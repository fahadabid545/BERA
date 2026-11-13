"""Development: files in a private folder on this computer, never served by the web server."""

import os
from pathlib import Path

from django.conf import settings

from .errors import StorageError, StoredFileMissing

FOLDER_MODE = 0o700
FILE_MODE = 0o600  # only the account running the app can read what is stored


def _path_for(key):
    root = Path(settings.PRIVATE_FILES_ROOT).resolve()
    path = (root / key).resolve()
    if root not in path.parents:  # a mistake in the code, never reachable from a request
        raise ValueError("A file key must stay inside the storage folder.")
    return path


def save(key, data):
    path = _path_for(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=FOLDER_MODE)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        with os.fdopen(descriptor, "wb") as stored:
            stored.write(data)
    except OSError as error:
        raise StorageError from error


def read(key):
    try:
        return _path_for(key).read_bytes()
    except FileNotFoundError as error:
        raise StoredFileMissing from error
    except OSError as error:
        raise StorageError from error


def delete(key):
    try:
        _path_for(key).unlink(missing_ok=True)
    except OSError as error:
        raise StorageError from error


def link_for(key, file_name, expires_seconds):
    """The local store has no address of its own: the caller makes a signed link instead."""
    return None
