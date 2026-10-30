"""Creating and reading the signed tokens. Knows nothing about sessions or requests."""

import hashlib
import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from rest_framework.exceptions import NotAuthenticated

from platform_settings.service import get_setting

from .kinds import ALGORITHM, AUDIENCES, ISSUER, KINDS, ROLES

ACCESS = "access"
REFRESH = "refresh"
# The claims every token must carry; a token missing any of them is refused.
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "jti", "sid", "typ", "role"]
# No genuine token is anywhere near this long; checking first keeps abuse cheap.
MAX_TOKEN_LENGTH = 4096


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(*, kind, token_type, user_id, role, company_id, session_id, now, lifetime):
    """Only the user, role, company, session and token identifiers go into a token."""
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCES[kind],
        "sub": str(user_id),
        "role": role,
        "sid": str(session_id),
        "jti": str(uuid.uuid4()),
        "typ": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=lifetime),
    }
    if company_id is not None:
        claims["cid"] = company_id
    return jwt.encode(claims, settings.TOKEN_SIGNING_SECRETS[kind], algorithm=ALGORITHM)


def read_token(token, *, kind, token_type):
    """The token's claims, or NotAuthenticated, whatever is wrong with it."""
    if kind not in KINDS or not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_LENGTH:
        raise NotAuthenticated()
    try:
        claims = jwt.decode(
            token,
            settings.TOKEN_SIGNING_SECRETS[kind],
            algorithms=[ALGORITHM],
            audience=AUDIENCES[kind],
            issuer=ISSUER,
            leeway=get_setting("tokens.clock_leeway_seconds"),
            options={"require": REQUIRED_CLAIMS},
        )
        if claims["typ"] != token_type or claims["role"] not in ROLES[kind]:
            raise NotAuthenticated()
        int(claims["sub"])
        uuid.UUID(claims["sid"])
        _check_company_claim(claims, kind)
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise NotAuthenticated() from error
    return claims


def _check_company_claim(claims, kind):
    has_company = "cid" in claims
    if has_company != (kind == "company") or (has_company and not isinstance(claims["cid"], int)):
        raise ValueError("company claim does not fit the kind")
