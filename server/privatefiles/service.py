"""The one place files are saved, read, removed and linked. Everything else in the app uses
these functions and never knows which store is behind them.

Keys are built only from identifiers the server made, never from anything a person typed, so a
file name can never choose where a file goes. A failed attempt is tried again after the waits in
`storage.retry_waits_seconds`; when they run out `StorageUnavailable` is raised and the caller
shows the file as failed.
"""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone

from platform_settings.service import get_setting

from . import local, r2
from .errors import InvalidLink, StorageError, StorageUnavailable, StoredFileMissing

logger = logging.getLogger(__name__)

LINK_SALT = "private-file-link"
SECONDS_PER_HOUR = 3600
LINK_PATH = "/api/files/{token}/"


def _backend():
    return r2 if settings.FILE_STORAGE_BACKEND == "r2" else local


def _with_retries(action):
    waits = list(get_setting("storage.retry_waits_seconds"))
    while True:
        try:
            return action()
        except StorageError:
            if not waits:
                logger.error("File storage failed after several attempts.")
                raise StorageUnavailable() from None
            logger.warning("File storage failed; trying again.")
            time.sleep(waits.pop(0))


def key_for_cv(company_id, cv_id):
    return f"cvs/{company_id}/{cv_id}"


def save_file(key, data):
    _with_retries(lambda: _backend().save(key, data))


def read_file(key):
    """The file's bytes. Raises `StoredFileMissing` when it is not there."""
    return _with_retries(lambda: _backend().read(key))


def delete_file(key):
    """Removes the file; a file that is already gone is fine."""
    _with_retries(lambda: _backend().delete(key))


def download_link(key, file_name):
    """A short-lived link to one file: `{"url", "expires_at"}`. Call it only after checking
    that the person may download this file (see `cvs/downloads.py`)."""
    hours = get_setting("storage.download_link_hours")
    expires_seconds = hours * SECONDS_PER_HOUR
    expires_at = timezone.now() + timedelta(seconds=expires_seconds)
    url = _with_retries(lambda: _backend().link_for(key, file_name, expires_seconds))
    if url is None:  # the local store: a signed link the download route reads back
        token = signing.dumps({"key": key, "name": file_name}, salt=LINK_SALT)
        url = LINK_PATH.format(token=token)
    return {"url": url, "expires_at": expires_at.isoformat()}


def read_for_link(token):
    """(bytes, file name) for a local link that is still valid; the Downloads route serves it.
    A link that was changed or has expired is refused."""
    try:
        claims = signing.loads(
            token,
            salt=LINK_SALT,
            max_age=get_setting("storage.download_link_hours") * SECONDS_PER_HOUR,
        )
    except signing.BadSignature:
        raise InvalidLink() from None
    return read_file(claims["key"]), claims["name"]


__all__ = [
    "InvalidLink",
    "StorageUnavailable",
    "StoredFileMissing",
    "delete_file",
    "download_link",
    "key_for_cv",
    "read_file",
    "read_for_link",
    "save_file",
]
