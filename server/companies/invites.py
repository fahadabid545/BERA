"""The owner invites colleagues; an invitee accepts and becomes a member.

The link in the email is a shared `LinkToken` (purpose team_invite). An invitation keeps its
email encrypted. Seats are counted as the people of the company who have not been removed plus
the invitations still open (pending and not expired); the limit is
the plan's team size (or the company's own override), which includes the owner. A company
with no plan yet keeps the platform setting `team.max_accounts_per_company`.
"""

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from activity import service as activity
from audit.service import record
from core.errors import AppError
from core.field_protection import normalize_email
from emailing.link_tokens import (
    consume_link_token,
    issue_link_token,
    link_refusal,
    retire_link_tokens,
)
from emailing.links import build_link
from emailing.models import LinkToken
from emailing.rendering import duration_text
from emailing.service import send_email
from plans.limits import check_team_size
from platform_settings.service import get_setting

from .models import Company, CompanyUser, Invitation

PURPOSE = LinkToken.Purpose.TEAM_INVITE
HOURS_PER_DAY = 24

ACCOUNT_EXISTS = "This email already has an account."
ALREADY_INVITED = "This email already has a pending invitation. Resend it instead."
COMPANY_SUSPENDED = "This company account is suspended. Please contact support."


def _open_tokens():
    """Link tokens that can still be used."""
    return LinkToken.objects.filter(
        purpose=PURPOSE,
        subject_id=OuterRef("token_subject"),
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
    )


def open_invitations(company):
    """Invitations that are pending and whose link has not run out."""
    return Invitation.objects.filter(company=company, status=Invitation.Status.PENDING).filter(
        Exists(_open_tokens())
    )


def seats_in_use(company, *, ignoring=None):
    people = CompanyUser.objects.filter(company=company).exclude(status=CompanyUser.Status.REMOVED)
    open_ones = open_invitations(company)
    if ignoring is not None:
        open_ones = open_ones.exclude(pk=ignoring.pk)
    return people.count() + open_ones.count()


def _lifetime_hours():
    return get_setting("tokens.team_invite_days") * HOURS_PER_DAY


def _send_invitation(invitation, inviter_name, company_name):
    hours = _lifetime_hours()
    retire_link_tokens(PURPOSE, invitation.token_subject)  # only the newest link works
    token = issue_link_token(PURPOSE, invitation.token_subject, hours)
    send_email(
        "team_invite",
        invitation.email,
        inviter_name=inviter_name,
        company_name=company_name,
        link=build_link("/accept-invite", token=token),
        expires_in=duration_text(hours // HOURS_PER_DAY, "day"),
    )


def invite_member(owner, email):
    """Invites an address to the owner's company, or says clearly why not."""
    email = normalize_email(email)
    with transaction.atomic():
        # One invitation at a time per company, so two at once cannot pass the limit together.
        company = Company.objects.select_for_update().get(pk=owner.company_id)
        if CompanyUser.objects.filter(email=email).exists():
            raise AppError("account_exists", ACCOUNT_EXISTS, status_code=409)
        if Invitation.objects.filter(
            company=company, email_lookup=email, status=Invitation.Status.PENDING
        ).exists():
            raise AppError("already_invited", ALREADY_INVITED, status_code=409)
        check_team_size(company.pk, seats_in_use(company)).raise_if_blocked()
        invitation = Invitation.objects.create(company=company, email=email, invited_by=owner)
        _send_invitation(invitation, owner.name, company.name)
        record("invite.sent", actor=owner, target=invitation)
        activity.record(
            "invite_sent",
            company_id=company.pk,
            actor=owner,
            target_kind="invitation",
            target_id=invitation.pk,
        )
    return invitation


def resend_invitation(invitation, inviter):
    """A new link and email; the old link stops working. An expired invitation can be resent
    only while there is a seat for it."""
    if invitation.status != Invitation.Status.PENDING:
        raise AppError("invitation_closed", "This invitation is no longer open.", status_code=409)
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=invitation.company_id)
        check_team_size(company.pk, seats_in_use(company, ignoring=invitation)).raise_if_blocked()
        _send_invitation(invitation, inviter.name, company.name)
        record("invite.resent", actor=inviter, target=invitation)
        activity.record(
            "invite_resent",
            company_id=company.pk,
            actor=inviter,
            target_kind="invitation",
            target_id=invitation.pk,
        )


def revoke_invitation(invitation, revoked_by):
    if invitation.status != Invitation.Status.PENDING:
        raise AppError("invitation_closed", "This invitation is no longer open.", status_code=409)
    invitation.status = Invitation.Status.REVOKED
    invitation.save(update_fields=["status"])
    retire_link_tokens(PURPOSE, invitation.token_subject)
    record("invite.revoked", actor=revoked_by, target=invitation)
    activity.record(
        "invite_revoked",
        company_id=invitation.company_id,
        actor=revoked_by,
        target_kind="invitation",
        target_id=invitation.pk,
    )


def describe_invitations(company):
    """The pending invitations of the company, newest first, for the Team page."""
    now = timezone.now()
    described = []
    for invitation in Invitation.objects.filter(
        company=company, status=Invitation.Status.PENDING
    ).order_by("-created_at"):
        latest = (
            LinkToken.objects.filter(purpose=PURPOSE, subject_id=invitation.token_subject)
            .order_by("-created_at")
            .first()
        )
        expires_at = latest.expires_at if latest else None
        expired = expires_at is None or latest.used_at is not None or expires_at <= now
        described.append(
            {
                "id": str(invitation.id),
                "email": invitation.email,
                "status": "expired" if expired else "pending",
                "expires_at": expires_at,
            }
        )
    return described


@transaction.atomic
def accept_invitation(token, name, password):
    """Spends the link, creates the member with the email already verified, and closes the
    invitation. If anything is refused, nothing is saved, so the link still works for another
    try (for example after choosing a stronger password)."""
    subject = consume_link_token(token, PURPOSE)
    invitation = (
        Invitation.objects.select_for_update()
        .select_related("company")
        .filter(token_subject=subject, status=Invitation.Status.PENDING)
        .first()
    )
    if invitation is None:
        raise link_refusal("link_invalid", "This link is not valid.")
    if invitation.company.status != Company.Status.ACTIVE:
        raise AppError("company_suspended", COMPANY_SUSPENDED, status_code=403)
    if CompanyUser.objects.filter(email=invitation.email).exists():
        raise AppError("account_exists", ACCOUNT_EXISTS, status_code=409)
    check_team_size(
        invitation.company_id, seats_in_use(invitation.company, ignoring=invitation)
    ).raise_if_blocked()

    member = CompanyUser(
        company=invitation.company,
        name=name,
        email=invitation.email,
        role=CompanyUser.Role.MEMBER,
        # Opening the link in their inbox proves the address, and accepting counts as
        # agreeing to the Terms and Privacy Policy.
        email_verified=True,
        terms_accepted_at=timezone.now(),
    )
    member.set_password(password)
    try:
        with transaction.atomic():
            member.save()
    except IntegrityError as error:  # the address was registered at the same moment
        raise AppError("account_exists", ACCOUNT_EXISTS, status_code=409) from error
    invitation.status = Invitation.Status.ACCEPTED
    invitation.save(update_fields=["status"])
    retire_link_tokens(PURPOSE, invitation.token_subject)
    record("invite.accepted", actor=member, target=invitation)
    activity.record(
        "invite_accepted",
        company_id=invitation.company_id,
        actor=member,
        target_kind="invitation",
        target_id=invitation.pk,
    )
    return member
