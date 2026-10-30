"""Encrypts personal data before it reaches the database, and finds it again by a hash.

Encryption uses a random value every time, so the same email encrypts differently on each
save and cannot be searched. Where a ticket needs a search (such as duplicate detection) a
second column holds a keyed hash of the normalised value; it cannot be reversed without
FIELD_HASH_KEY. Both keys come from settings and are never stored beside the data.
"""

import base64
import functools
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

from .errors import AppError

# A version byte in front of every stored value lets a later key change read old values.
FORMAT_VERSION = b"\x01"
NONCE_BYTES = 12
KEY_BYTES = 32


@functools.lru_cache(maxsize=8)
def _derived_key(secret, label):
    """One configured secret gives one key per job, so a leak of one never opens the other."""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=None, info=label.encode()).derive(
        secret.encode()
    )


def encrypt_text(plain_text, purpose):
    """`purpose` (for example "candidate.email") is sealed in, so a value copied into another
    column fails to open there."""
    nonce = os.urandom(NONCE_BYTES)
    key = _derived_key(settings.FIELD_KEYS["encryption"], "encryption")
    sealed = AESGCM(key).encrypt(nonce, plain_text.encode(), purpose.encode())
    return base64.urlsafe_b64encode(FORMAT_VERSION + nonce + sealed).decode()


def decrypt_text(stored_text, purpose):
    try:
        raw = base64.urlsafe_b64decode(stored_text.encode())
        if raw[:1] != FORMAT_VERSION:
            raise ValueError("unknown format")
        nonce, sealed = raw[1 : 1 + NONCE_BYTES], raw[1 + NONCE_BYTES :]
        key = _derived_key(settings.FIELD_KEYS["encryption"], "encryption")
        return AESGCM(key).decrypt(nonce, sealed, purpose.encode()).decode()
    except (InvalidTag, ValueError) as problem:
        # Wrong key, damaged value or a value moved to another column. The reason is
        # kept out of the message so nothing about the data or keys is revealed.
        raise AppError(
            "protected_value_unreadable", "Something went wrong.", status_code=500
        ) from problem


def lookup_hash(normalised_text, purpose):
    key = _derived_key(settings.FIELD_KEYS["hash"], "lookup")
    message = f"{purpose}\0{normalised_text}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def normalize_email(value):
    return value.strip().lower()


def normalize_phone(value):
    """Digits only, keeping a leading +, so "+1 (555) 010-0100" and "+15550100100" match."""
    digits = "".join(character for character in value if character.isdigit())
    return ("+" if value.strip().startswith("+") else "") + digits
