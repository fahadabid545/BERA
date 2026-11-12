"""Starting, checking, renewing and ending sign-ins. The only code that touches Session rows."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Case, CharField, Exists, OuterRef, Q, Subquery, When
from django.utils import timezone
from rest_framework.exceptions import NotAuthenticated

from adminusers.models import AdminUser
from audit.security import record_security_event
from companies.models import Company, CompanyUser
from platform_settings.service import get_setting

from .kinds import ADMIN, COMPANY, KINDS, ROLES
from .models import RetiredRefreshToken, Session
from .tokens import ACCESS, REFRESH, create_token, hash_token, read_token

logger = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * 60
SECONDS_PER_DAY = 24 * 60 * 60


class RevokeReason:
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    REMOVED = "removed"
    PASSWORD_CHANGED = "password_changed"
    ROLE_CHANGED = "role_changed"
    BLOCKED = "blocked"
    COMPANY_SUSPENDED = "company_suspended"
    REFRESH_REUSE = "refresh_reuse"


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    session_id: str
    access_seconds: int
    refresh_seconds: int


@dataclass(frozen=True)
class SignedInUser:
    """Who a verified request belongs to. Stands in for Django's user object on requests."""

    user_id: int
    role: str
    company_id: int | None
    kind: str
    session_id: str
    is_authenticated = True


def _account_is_active():
    """True in a query only while the account exists and is not blocked or removed, and, for
    a company user, still belongs to the session's company while that company is active.

    Each kind of session is checked in its own table, so a company user's id can never
    stand in for an admin's."""
    company_user = CompanyUser.objects.filter(
        id=OuterRef("user_id"),
        company_id=OuterRef("company_id"),
        status=CompanyUser.Status.ACTIVE,
        company__status=Company.Status.ACTIVE,
    )
    admin_user = AdminUser.objects.filter(id=OuterRef("user_id"), status=AdminUser.Status.ACTIVE)
    return (Q(kind=COMPANY) & Q(Exists(company_user))) | (Q(kind=ADMIN) & Q(Exists(admin_user)))


def _current_role():
    """The role stored for the person now, so a change applies at once, not at the next
    token renewal."""
    company_role = CompanyUser.objects.filter(id=OuterRef("user_id")).values("role")[:1]
    admin_role = AdminUser.objects.filter(id=OuterRef("user_id")).values("role")[:1]
    return Case(
        When(kind=COMPANY, then=Subquery(company_role)),
        default=Subquery(admin_role),
        output_field=CharField(),
    )


def _check_who(kind, role, company_id):
    """Programming mistakes in the login code, not user mistakes, so they stop loudly."""
    if kind not in KINDS:
        raise ValueError(f"Unknown sign-in kind: {kind}")
    if role not in ROLES[kind]:
        raise ValueError(f"Unknown {kind} role: {role}")
    if (kind == COMPANY) != (company_id is not None):
        raise ValueError("Company sign-ins need a company id and admin sign-ins must not have one.")


def _lifetimes(kind):
    if kind == ADMIN:
        return {
            ACCESS: get_setting("tokens.admin_access_minutes") * SECONDS_PER_MINUTE,
            REFRESH: get_setting("tokens.admin_refresh_hours") * SECONDS_PER_HOUR,
        }
    return {
        ACCESS: get_setting("tokens.access_minutes") * SECONDS_PER_MINUTE,
        REFRESH: get_setting("tokens.refresh_days") * SECONDS_PER_DAY,
    }


def _issue_pair(session, role, now):
    lifetimes = _lifetimes(session.kind)
    tokens = {
        token_type: create_token(
            kind=session.kind,
            token_type=token_type,
            user_id=session.user_id,
            role=role,
            company_id=session.company_id,
            session_id=session.id,
            now=now,
            lifetime=lifetime,
        )
        for token_type, lifetime in lifetimes.items()
    }
    return tokens, lifetimes


def _finish(session, role, now):
    tokens, lifetimes = _issue_pair(session, role, now)
    session.refresh_token_hash = hash_token(tokens[REFRESH])
    session.expires_at = now + timedelta(seconds=lifetimes[REFRESH])
    return IssuedTokens(
        access_token=tokens[ACCESS],
        refresh_token=tokens[REFRESH],
        session_id=str(session.id),
        access_seconds=lifetimes[ACCESS],
        refresh_seconds=lifetimes[REFRESH],
    )


def start_session(*, user_id, role, company_id, kind):
    """Called by the login code once it has checked who the person is."""
    _check_who(kind, role, company_id)
    session = Session(user_id=user_id, kind=kind, company_id=company_id)
    issued = _finish(session, role, timezone.now())
    session.save()
    return issued


def verify_access_token(token, kind):
    """The signed-in user, or NotAuthenticated.

    One lookup confirms the session is live and its account is still active, so a removed or
    blocked person is refused at once even with an unexpired token.
    """
    claims = read_token(token, kind=kind, token_type=ACCESS)
    company_id = claims.get("cid")
    current_role = (
        Session.objects.filter(
            _account_is_active(),
            id=claims["sid"],
            kind=kind,
            user_id=int(claims["sub"]),
            company_id=company_id,
            status=Session.Status.ACTIVE,
            expires_at__gt=timezone.now(),
        )
        .annotate(current_role=_current_role())
        .values_list("current_role", flat=True)
        .first()
    )
    if current_role is None:
        raise NotAuthenticated()
    return SignedInUser(
        user_id=int(claims["sub"]),
        role=current_role,
        company_id=company_id,
        kind=kind,
        session_id=claims["sid"],
    )


def refresh_session(token, kind):
    """Swap a refresh token for a new pair. The old refresh token never works again."""
    claims = read_token(token, kind=kind, token_type=REFRESH)
    digest = hash_token(token)
    now = timezone.now()
    reuse_detected = False
    with transaction.atomic():
        session = (
            Session.objects.select_for_update(of=("self",))
            .filter(_account_is_active(), id=claims["sid"], kind=kind, user_id=int(claims["sub"]))
            .annotate(current_role=_current_role())
            .first()
        )
        if session and session.status == Session.Status.ACTIVE and session.expires_at > now:
            if session.refresh_token_hash == digest:
                RetiredRefreshToken.objects.create(token_hash=digest, session=session)
                issued = _finish(session, session.current_role, now)
                session.save(update_fields=["refresh_token_hash", "expires_at"])
                return issued
            reuse_detected = session.retired_tokens.filter(token_hash=digest).exists()
            if reuse_detected:
                session.status = Session.Status.REVOKED
                session.revoke_reason = RevokeReason.REFRESH_REUSE
                session.save(update_fields=["status", "revoke_reason"])
    # Raised after the block so ending the session is saved, not rolled back with the error.
    if reuse_detected:
        record_security_event("security.token_reuse", actor=session)
        logger.warning("Used refresh token presented again; the session was ended")
    raise NotAuthenticated()


def _revoke(sessions, reason):
    count = sessions.filter(status=Session.Status.ACTIVE).update(
        status=Session.Status.REVOKED, revoke_reason=reason
    )
    logger.info("Ended %s session(s): %s", count, reason)
    return count


def revoke_session(session_id, reason):
    return _revoke(Session.objects.filter(id=session_id), reason)


def end_session_of_refresh_token(token, kind):
    """Logout: ends the session this refresh token belongs to. A token that is forged, from
    another kind of sign-in or already past its time has nothing left to end, which is fine."""
    try:
        claims = read_token(token, kind=kind, token_type=REFRESH)
    except NotAuthenticated:
        return 0
    sessions = Session.objects.filter(id=claims["sid"], kind=kind, user_id=int(claims["sub"]))
    return _revoke(sessions, RevokeReason.LOGOUT)


def revoke_user_sessions(user_id, reason, *, kind=None):
    sessions = Session.objects.filter(user_id=user_id)
    return _revoke(sessions.filter(kind=kind) if kind else sessions, reason)


def revoke_company_sessions(company_id, reason):
    return _revoke(Session.objects.filter(kind=COMPANY, company_id=company_id), reason)
