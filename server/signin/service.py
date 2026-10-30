"""Starting, checking, renewing and ending sign-ins. The only code that touches Session rows."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotAuthenticated

from platform_settings.service import get_setting

from .kinds import COMPANY, KINDS, ROLES
from .models import RetiredRefreshToken, Session
from .tokens import ACCESS, REFRESH, create_token, hash_token, read_token

logger = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60
SECONDS_PER_DAY = 24 * 60 * 60


class RevokeReason:
    LOGOUT = "logout"
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


def _check_who(kind, role, company_id):
    """Programming mistakes in the login code, not user mistakes, so they stop loudly."""
    if kind not in KINDS:
        raise ValueError(f"Unknown sign-in kind: {kind}")
    if role not in ROLES[kind]:
        raise ValueError(f"Unknown {kind} role: {role}")
    if (kind == COMPANY) != (company_id is not None):
        raise ValueError("Company sign-ins need a company id and admin sign-ins must not have one.")


def _issue_pair(session, role, now):
    lifetimes = {
        ACCESS: get_setting("tokens.access_minutes") * SECONDS_PER_MINUTE,
        REFRESH: get_setting("tokens.refresh_days") * SECONDS_PER_DAY,
    }
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
    """The signed-in user, or NotAuthenticated. One indexed lookup confirms the session is live."""
    claims = read_token(token, kind=kind, token_type=ACCESS)
    company_id = claims.get("cid")
    still_active = Session.objects.filter(
        id=claims["sid"],
        kind=kind,
        user_id=int(claims["sub"]),
        company_id=company_id,
        status=Session.Status.ACTIVE,
        expires_at__gt=timezone.now(),
    ).exists()
    if not still_active:
        raise NotAuthenticated()
    return SignedInUser(
        user_id=int(claims["sub"]),
        role=claims["role"],
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
            Session.objects.select_for_update()
            .filter(id=claims["sid"], kind=kind, user_id=int(claims["sub"]))
            .first()
        )
        if session and session.status == Session.Status.ACTIVE and session.expires_at > now:
            if session.refresh_token_hash == digest:
                RetiredRefreshToken.objects.create(token_hash=digest, session=session)
                issued = _finish(session, claims["role"], now)
                session.save(update_fields=["refresh_token_hash", "expires_at"])
                return issued
            reuse_detected = session.retired_tokens.filter(token_hash=digest).exists()
            if reuse_detected:
                session.status = Session.Status.REVOKED
                session.revoke_reason = RevokeReason.REFRESH_REUSE
                session.save(update_fields=["status", "revoke_reason"])
    # Raised after the block so ending the session is saved, not rolled back with the error.
    if reuse_detected:
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


def revoke_user_sessions(user_id, reason, *, kind=None):
    sessions = Session.objects.filter(user_id=user_id)
    return _revoke(sessions.filter(kind=kind) if kind else sessions, reason)


def revoke_company_sessions(company_id, reason):
    return _revoke(Session.objects.filter(kind=COMPANY, company_id=company_id), reason)
