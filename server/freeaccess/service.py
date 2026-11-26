"""Giving, extending and taking away free access.

Everything here works on `FreeAccess` and `FreeAccessInvite` only. It never reads or changes a
subscription or an admin account, which is what keeps the three ways of having access apart:
revoking one leaves the others as they were. Every change is in the audit log. Email invites only
count for the company owner's verified address, so nobody gets access by typing someone else's
address; a code is kept as a hash and shown once.
"""

import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from audit.service import record
from companies.models import Company, CompanyUser
from core.errors import AppError
from emailing.links import build_link
from emailing.rendering import format_moment
from emailing.service import send_email
from plans import trials
from plans.models import Plan
from platform_settings.service import get_setting

from . import entitlement
from .models import FreeAccess, FreeAccessInvite

Kind = FreeAccessInvite.Kind
PREFIX = "BETA"
NOT_USABLE_CODE = trials.NOT_USABLE_CODE
NOT_USABLE = trials.NOT_USABLE  # one message for every code that cannot be used
GROUP, GROUPS = trials.GROUP, 3


def _problem(field, message):
    return AppError("invalid_free_access", message, status_code=400, fields={field: message})


def _check_days(days):
    most = get_setting("beta.max_access_days")
    if not 1 <= days <= most:
        raise _problem("access_days", f"Use 1 to {most} days.")


def _owner(company_id):
    return CompanyUser.objects.filter(
        company_id=company_id, role=CompanyUser.Role.OWNER, status=CompanyUser.Status.ACTIVE
    ).first()


def _email_the_owner(grant, template):
    owner = _owner(grant.company_id)
    if owner is not None and grant.ends_at is not None:
        send_email(
            template,
            owner.email,
            name=owner.name,
            when=format_moment(grant.ends_at),
            link=build_link("/company"),
        )


def _grant(company_id, invite, *, source):
    """Gives the company the access of an invite once. Returns None when it already has this
    invite's access (even a revoked one: a revoked access is never given back by itself) or an
    access of the same kind that is still running."""
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=company_id)
        if FreeAccess.objects.filter(company_id=company_id, invite=invite).exists():
            return None
        kind = (
            FreeAccess.Kind.PERMITTED
            if invite.kind == Kind.PERMITTED_EMAIL
            else FreeAccess.Kind.BETA
        )
        if entitlement.active_grants(company_id).filter(kind=kind).exists():
            return None
        now = timezone.now()
        grant = FreeAccess.objects.create(
            company_id=company_id,
            kind=kind,
            invite=invite,
            plan=invite.plan if kind == FreeAccess.Kind.PERMITTED else None,
            started_at=now,
            ends_at=now + timedelta(days=invite.access_days)
            if kind == FreeAccess.Kind.BETA
            else None,
        )
        record(
            "free_access.granted",
            company_id=company_id,
            details={"invite": invite.pk, "kind": kind, "source": source},
        )
    if kind == FreeAccess.Kind.BETA:
        _email_the_owner(grant, "beta_access_granted")
    return grant


# --- the invites a super admin makes -----------------------------------------------------------


def _new_code():
    body = "".join(secrets.choice(trials.ALPHABET) for _ in range(GROUP * GROUPS))
    return "-".join([PREFIX, *(body[i : i + GROUP] for i in range(0, len(body), GROUP))])


def invite_email(admin, *, kind, email, access_days=None, plan_id=None, label=""):
    """An email address that gets free access when its owner has signed up and verified it (now,
    if they already have). `kind` is beta_email (limited, for some days) or permitted_email (a
    chosen plan's full limits until revoked)."""
    plan = None
    if kind == Kind.BETA_EMAIL:
        _check_days(access_days)
    else:
        plan = Plan.objects.filter(pk=plan_id, status=Plan.Status.ACTIVE).first()
        if plan is None:
            raise _problem("plan_id", "Choose one of the active plans.")
        access_days = None
    if FreeAccessInvite.objects.filter(kind=kind, email_lookup=email, enabled=True).exists():
        raise _problem("email", "This address already has an invite.")
    with transaction.atomic():
        invite = FreeAccessInvite.objects.create(
            kind=kind, label=label, email=email, access_days=access_days, plan=plan
        )
        record(
            "admin.free_access_invite_created",
            actor=admin,
            details={"invite": invite.pk, "kind": kind},
        )
    apply_for_email(email)
    return invite


def invite_code(admin, *, label, access_days, max_uses, redeem_until=None):
    """A code to share. Returns (invite, the code); the code is never shown again."""
    _check_days(access_days)
    most_uses = get_setting("beta.max_code_uses")
    if not 1 <= max_uses <= most_uses:
        raise _problem("max_uses", f"Use 1 to {most_uses} uses.")
    if redeem_until is not None and redeem_until <= timezone.now():
        raise _problem("redeem_until", "The last day to use the code must be in the future.")
    code = _new_code()
    with transaction.atomic():
        invite = FreeAccessInvite.objects.create(
            kind=Kind.BETA_CODE,
            label=label,
            code_hash=trials.hash_of(code),
            access_days=access_days,
            max_uses=max_uses,
            redeem_until=redeem_until,
        )
        record(
            "admin.free_access_invite_created",
            actor=admin,
            details={"invite": invite.pk, "kind": invite.kind, "uses": max_uses},
        )
    return invite, code


def _get_invite(invite_id):
    invite = FreeAccessInvite.objects.select_for_update().filter(pk=invite_id).first()
    if invite is None:
        raise AppError("free_access_not_found", "There is no such invite.", status_code=404)
    return invite


def _revoke(grant, admin):
    grant.revoked_at = timezone.now()
    grant.save(update_fields=["revoked_at"])
    record(
        "admin.free_access_revoked",
        actor=admin,
        company_id=grant.company_id,
        details={"kind": grant.kind},
    )


def switch_invite(admin, invite_id, *, enabled, also_revoke_users=False):
    """Switches an invite on or off. Off stops anyone new using it; with `also_revoke_users` the
    access it already gave is taken back as well. Other invites are never touched."""
    with transaction.atomic():
        invite = _get_invite(invite_id)
        if invite.enabled == enabled and not also_revoke_users:
            raise AppError("nothing_changed", "Nothing was changed.", status_code=400)
        invite.enabled = enabled
        invite.save(update_fields=["enabled"])
        revoked = 0
        if also_revoke_users:
            for grant in invite.grants.filter(revoked_at__isnull=True):
                _revoke(grant, admin)
                revoked += 1
        record(
            "admin.free_access_invite_switched",
            actor=admin,
            details={"invite": invite.pk, "enabled": enabled, "count": revoked},
        )
    return invite


def delete_invite(admin, invite_id):
    """Removes an invite nobody has used. One that gave access stays (switch it off instead), so
    the record of who got access and why is never lost."""
    with transaction.atomic():
        invite = _get_invite(invite_id)
        if invite.grants.exists():
            raise AppError(
                "free_access_invite_used",
                "This invite has been used, so it cannot be deleted. Switch it off instead.",
                status_code=409,
            )
        kind = invite.kind
        invite.delete()
        record(
            "admin.free_access_invite_deleted",
            actor=admin,
            details={"invite": invite_id, "kind": kind},
        )


# --- when an email address becomes a company's owner's ------------------------------------------


def apply_for_email(email):
    """Gives access to the company whose owner has verified this address, if an invite for it
    is on. Called when an invite is made and when an address is verified."""
    owner = (
        CompanyUser.objects.filter(
            email=email.strip().lower(),
            email_verified=True,
            role=CompanyUser.Role.OWNER,
            status=CompanyUser.Status.ACTIVE,
        )
        .only("company_id")
        .first()
    )
    if owner is not None:
        apply_for_company(owner.company_id)


def apply_for_company(company_id):
    """Applies every email invite that matches the owner's verified address."""
    owner = _owner(company_id)
    if owner is None or not owner.email_verified:
        return
    invites = FreeAccessInvite.objects.filter(
        kind__in=[Kind.BETA_EMAIL, Kind.PERMITTED_EMAIL], email_lookup=owner.email, enabled=True
    )
    for invite in invites:
        _grant(company_id, invite, source="email")


# --- a company redeems a code ------------------------------------------------------------------


def usable_code(code):
    """The invite for a code that can still be used, else None. It never says why not."""
    invite = FreeAccessInvite.objects.filter(
        kind=Kind.BETA_CODE, code_hash=trials.hash_of(code)
    ).first()
    return invite if invite is not None and _usable(invite) else None


def _usable(invite, now=None):
    now = now or timezone.now()
    return (
        invite.enabled
        and (invite.redeem_until is None or invite.redeem_until > now)
        and invite.grants.count() < invite.max_uses
    )


def redeem_code(company_id, code):
    """The owner joins the beta with a code. Every code that cannot be used (unknown, off, ended,
    used up, or the company already has beta access) gets the same refusal."""
    with transaction.atomic():
        invite = (
            FreeAccessInvite.objects.select_for_update()
            .filter(kind=Kind.BETA_CODE, code_hash=trials.hash_of(code))
            .first()
        )
        grant = _grant(company_id, invite, source="code") if invite and _usable(invite) else None
    if grant is None:
        raise AppError(NOT_USABLE_CODE, NOT_USABLE, status_code=400)
    return grant


# --- taking away and extending -----------------------------------------------------------------


def _get_grant(grant_id):
    grant = FreeAccess.objects.select_for_update().filter(pk=grant_id).first()
    if grant is None:
        raise AppError("free_access_not_found", "There is no such access.", status_code=404)
    return grant


def revoke(admin, grant_id):
    with transaction.atomic():
        grant = _get_grant(grant_id)
        if grant.revoked_at is not None:
            raise AppError("nothing_changed", "Nothing was changed.", status_code=400)
        _revoke(grant, admin)
    return grant


def change_plan(admin, grant_id, *, plan_id):
    """Gives a running permitted access another plan. Beta access has no plan to change."""
    plan = Plan.objects.filter(pk=plan_id, status=Plan.Status.ACTIVE).first()
    if plan is None:
        raise _problem("plan_id", "Choose one of the active plans.")
    with transaction.atomic():
        grant = _get_grant(grant_id)
        if grant.kind != FreeAccess.Kind.PERMITTED or grant.revoked_at is not None:
            raise AppError(
                "nothing_changed", "Only a running permitted access has a plan.", status_code=400
            )
        grant.plan = plan
        grant.save(update_fields=["plan"])
        record(
            "admin.free_access_plan_changed",
            actor=admin,
            company_id=grant.company_id,
            details={"plan_id": plan.pk},
        )
    return grant


def revoke_all_beta(admin):
    """Takes back every running beta access. Permitted access is a different thing and stays."""
    with transaction.atomic():
        grants = list(
            FreeAccess.objects.select_for_update().filter(
                kind=FreeAccess.Kind.BETA, revoked_at__isnull=True
            )
        )
        for grant in grants:
            _revoke(grant, admin)
        record("admin.free_access_revoked_all", actor=admin, details={"count": len(grants)})
    return len(grants)


def _extend(grant, days, admin):
    start = max(grant.ends_at, timezone.now())  # an ended access is extended from today
    grant.ends_at = start + timedelta(days=days)
    grant.save(update_fields=["ends_at"])
    record(
        "admin.free_access_extended",
        actor=admin,
        company_id=grant.company_id,
        details={"days": days},
    )


def extend(admin, grant_id, *, days):
    """Gives a beta access more days and emails the owner the new end date."""
    _check_days(days)
    with transaction.atomic():
        grant = _get_grant(grant_id)
        if grant.kind != FreeAccess.Kind.BETA or grant.revoked_at is not None:
            raise AppError(
                "cannot_extend", "Only a running beta access can be extended.", status_code=409
            )
        _extend(grant, days, admin)
    _email_the_owner(grant, "beta_access_extended")
    return grant


def extend_invite(admin, invite_id, *, days):
    """Extends every beta access that came from one invite that has not been revoked."""
    _check_days(days)
    with transaction.atomic():
        invite = _get_invite(invite_id)
        grants = list(
            invite.grants.select_for_update().filter(
                kind=FreeAccess.Kind.BETA, revoked_at__isnull=True
            )
        )
        for grant in grants:
            _extend(grant, days, admin)
    for grant in grants:
        _email_the_owner(grant, "beta_access_extended")
    return len(grants)


# --- what the admin sees -----------------------------------------------------------------------


def describe_invite(invite):
    return {
        "id": invite.pk,
        "kind": invite.kind,
        "label": invite.label,
        "email": invite.email or None,
        "plan": {"id": invite.plan_id, "name": invite.plan.name} if invite.plan_id else None,
        "access_days": invite.access_days,
        "max_uses": invite.max_uses,
        "uses": invite.grants.count(),
        "redeem_until": invite.redeem_until.isoformat() if invite.redeem_until else None,
        "enabled": invite.enabled,
        "created_at": invite.created_at.isoformat(),
    }


def list_invites():
    return [
        describe_invite(invite)
        for invite in FreeAccessInvite.objects.select_related("plan").prefetch_related("grants")
    ]


def status_of(grant, now=None):
    now = now or timezone.now()
    if grant.revoked_at is not None:
        return "revoked"
    if grant.ends_at is not None and grant.ends_at <= now:
        return "ended"
    return "active"


def describe_grant(grant):
    company = Company.objects.filter(pk=grant.company_id).values("id", "name").first()
    owner = _owner(grant.company_id)
    return {
        "id": grant.pk,
        "kind": grant.kind,
        "status": status_of(grant),
        "company": {"id": str(company["id"]), "name": company["name"]} if company else None,
        "owner": {"name": owner.name, "email": owner.email} if owner else None,
        "invite": {"id": grant.invite_id, "label": grant.invite.label, "kind": grant.invite.kind},
        "plan": {"id": grant.plan_id, "name": grant.plan.name} if grant.plan_id else None,
        "started_at": grant.started_at.isoformat(),
        "ends_at": grant.ends_at.isoformat() if grant.ends_at else None,
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
    }


def list_grants(*, kind=None, status=None, page=1, page_size=None):
    """One page of free accesses, newest first, and how many there are."""
    size = page_size or get_setting("free_access.page_size")
    grants = FreeAccess.objects.select_related("invite", "plan")
    if kind:
        grants = grants.filter(kind=kind)
    now = timezone.now()
    if status == "active":
        grants = grants.filter(revoked_at__isnull=True).exclude(ends_at__lte=now)
    elif status == "revoked":
        grants = grants.filter(revoked_at__isnull=False)
    elif status == "ended":
        grants = grants.filter(revoked_at__isnull=True, ends_at__lte=now)
    total = grants.count()
    chosen = grants[(page - 1) * size : page * size]
    return {
        "total": total,
        "page": page,
        "page_size": size,
        "items": [describe_grant(g) for g in chosen],
    }
