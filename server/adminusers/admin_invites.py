"""A super admin invites someone to become an admin; the invitee accepts and chooses a password.

The link in the email is a shared `LinkToken` (purpose admin_invite), single use, and it is the
only secret in the email. Accepting creates the account with the role the inviter chose. The new
admin sets up two-step verification at their first sign-in: that is the rule for every admin
(signin/login_session.py), not something this module switches on.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

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
from platform_settings.service import get_setting

from .models import AdminInvitation, AdminUser

PURPOSE = LinkToken.Purpose.ADMIN_INVITE
HOURS_PER_DAY = 24

ACCOUNT_EXISTS = "This email already has an admin account."
ALREADY_INVITED = "This email already has a pending invitation. Resend it instead."
CLOSED = "This invitation is no longer open."


def _lifetime_hours():
    return get_setting("tokens.admin_invite_days") * HOURS_PER_DAY


def _send(invitation, inviter):
    hours = _lifetime_hours()
    retire_link_tokens(PURPOSE, invitation.token_subject)  # only the newest link works
    token = issue_link_token(PURPOSE, invitation.token_subject, hours)
    send_email(
        "admin_invite",
        invitation.email,
        inviter_name=inviter.name,
        role_name=invitation.role,
        link=build_link("/admin/accept-invite", token=token),
        expires_in=duration_text(hours // HOURS_PER_DAY, "day"),
    )


def invite_admin(inviter, *, name, email, role, reason):
    """Invites an address to be an admin, or says clearly why not. Any existing admin account
    with that address (active, blocked or removed) is a refusal: re-enable that account instead."""
    email = normalize_email(email)
    with transaction.atomic():
        if AdminUser.objects.filter(email=email).exists():
            raise AppError("account_exists", ACCOUNT_EXISTS, status_code=409)
        if AdminInvitation.objects.filter(
            email_lookup=email, status=AdminInvitation.Status.PENDING
        ).exists():
            raise AppError("already_invited", ALREADY_INVITED, status_code=409)
        invitation = AdminInvitation.objects.create(
            name=name, email=email, role=role, invited_by=inviter
        )
        _send(invitation, inviter)
        record(
            "admin.invited",
            actor=inviter,
            reason=reason,
            details={"invitation_id": invitation.pk, "role": role},
        )
    return invitation


def _pending(invitation_id):
    invitation = AdminInvitation.objects.select_for_update().filter(pk=invitation_id).first()
    if invitation is None:
        return None
    if invitation.status != AdminInvitation.Status.PENDING:
        raise AppError("invitation_closed", CLOSED, status_code=409)
    return invitation


def resend_invite(inviter, invitation_id):
    """A new link and email; the old link stops working."""
    with transaction.atomic():
        invitation = _pending(invitation_id)
        if invitation is None:
            return None
        _send(invitation, inviter)
        record(
            "admin.invite_resent",
            actor=inviter,
            details={"invitation_id": invitation.pk, "role": invitation.role},
        )
    return invitation


def revoke_invite(inviter, invitation_id):
    with transaction.atomic():
        invitation = _pending(invitation_id)
        if invitation is None:
            return None
        invitation.status = AdminInvitation.Status.REVOKED
        invitation.save(update_fields=["status"])
        retire_link_tokens(PURPOSE, invitation.token_subject)
        record(
            "admin.invite_revoked",
            actor=inviter,
            details={"invitation_id": invitation.pk, "role": invitation.role},
        )
    return invitation


@transaction.atomic
def accept_invite(token, password):
    """Spends the link and creates the admin. If anything is refused nothing is saved, so the
    link still works for another try (for example after choosing a stronger password)."""
    subject = consume_link_token(token, PURPOSE)
    invitation = (
        AdminInvitation.objects.select_for_update()
        .filter(token_subject=subject, status=AdminInvitation.Status.PENDING)
        .first()
    )
    if invitation is None:
        raise link_refusal("link_invalid", "This link is not valid.")
    if AdminUser.objects.filter(email=invitation.email).exists():
        raise AppError("account_exists", ACCOUNT_EXISTS, status_code=409)
    admin = AdminUser(name=invitation.name, email=invitation.email, role=invitation.role)
    admin.set_password(password)
    try:
        with transaction.atomic():
            admin.save()
    except IntegrityError as error:  # the address was taken at the same moment
        raise AppError("account_exists", ACCOUNT_EXISTS, status_code=409) from error
    invitation.status = AdminInvitation.Status.ACCEPTED
    invitation.save(update_fields=["status"])
    retire_link_tokens(PURPOSE, invitation.token_subject)
    record(
        "admin.invite_accepted",
        actor=admin,
        details={"invitation_id": invitation.pk, "role": admin.role},
    )
    return admin


def describe_invitations():
    """The invitations still waiting, newest first. One whose link ran out is "expired": it can be
    resent."""
    now = timezone.now()
    described = []
    for invitation in AdminInvitation.objects.filter(
        status=AdminInvitation.Status.PENDING
    ).order_by("-created_at", "-id"):
        newest = (
            LinkToken.objects.filter(purpose=PURPOSE, subject_id=invitation.token_subject)
            .order_by("-created_at")
            .first()
        )
        expires_at = newest.expires_at if newest else None
        expired = newest is None or newest.used_at is not None or expires_at <= now
        described.append(
            {
                "id": invitation.pk,
                "name": invitation.name,
                "email": invitation.email,
                "role": invitation.role,
                "status": "expired" if expired else "pending",
                "expires_at": expires_at,
            }
        )
    return described


def describe_admins():
    return [
        {
            "id": admin.pk,
            "name": admin.name,
            "email": admin.email,
            "role": admin.role,
            "status": admin.status,
            "two_step_enabled": admin.two_step_enabled,
        }
        for admin in AdminUser.objects.exclude(status=AdminUser.Status.REMOVED).order_by(
            "name", "id"
        )
    ]
