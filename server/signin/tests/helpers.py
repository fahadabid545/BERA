"""Builds tokens the way an attacker or a faulty server might, for the tests."""

import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

from signin.kinds import ALGORITHM, AUDIENCES, ISSUER


def forge(
    kind="company", *, secret=None, algorithm=ALGORITHM, issued_ago=0, lifetime=900, **overrides
):
    """A token with the right shape; keyword arguments change or (set to None) remove claims."""
    now = timezone.now() - timedelta(seconds=issued_ago)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCES[kind],
        "sub": "7",
        "role": "owner" if kind == "company" else "super",
        "sid": str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(seconds=lifetime),
    }
    if kind == "company":
        claims["cid"] = 3
    claims.update(overrides)
    claims = {name: value for name, value in claims.items() if value is not None}
    key = secret if secret is not None else settings.TOKEN_SIGNING_SECRETS[kind]
    return jwt.encode(claims, key, algorithm=algorithm)
