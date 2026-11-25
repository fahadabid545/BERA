"""The backup encryption keys, as configured: one current key with an id, and older keys that are
kept only so older backups still open. Never printed or logged."""

import re

from django.conf import settings

from config.environment import MIN_SIGNING_SECRET_LENGTH

from .errors import BackupFailure

KEY_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _previous_keys(text):
    """`id=key,id=key`."""
    pairs = [item.split("=", 1) for item in text.split(",") if item.strip()]
    if any(len(pair) != 2 for pair in pairs):
        raise BackupFailure("configuration")
    return {key_id.strip(): key.strip() for key_id, key in pairs}


def key_ring():
    """(current key id, {key id: key}), checked: ids are plain, keys long enough, ids distinct."""
    current_id = settings.BACKUP_ENCRYPTION_KEY_ID.strip()
    current_key = settings.BACKUP_ENCRYPTION_KEY.strip()
    keys = {current_id: current_key, **_previous_keys(settings.BACKUP_PREVIOUS_KEYS)}
    previous_count = len(_previous_keys(settings.BACKUP_PREVIOUS_KEYS))
    if (
        not KEY_ID.match(current_id)
        or len(keys) != previous_count + 1
        or any(not KEY_ID.match(key_id) for key_id in keys)
        or any(len(key) < MIN_SIGNING_SECRET_LENGTH for key in keys.values())
    ):
        raise BackupFailure("configuration")
    return current_id, keys
