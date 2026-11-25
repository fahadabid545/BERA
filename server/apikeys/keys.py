"""Making and recognising keys. A key looks like `bera_live_` followed by random characters; the
fixed start lets secret scanners find a leaked one."""

import hashlib
import secrets

PREFIX = "bera_live_"
RANDOM_BYTES = 32


def new_token():
    return PREFIX + secrets.token_urlsafe(RANDOM_BYTES)


def hash_of(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
