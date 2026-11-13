"""The one place files are saved, read and removed. Today it is a private local folder
(`PRIVATE_FILES_ROOT`, never served by the web server); Private file storage replaces the body
of these three functions with the S3-compatible store and keeps their names.

The key is built only from identifiers the server made, never from anything a person typed, so a
file name can never choose where a file goes."""

from pathlib import Path

from django.conf import settings


def _path_for(key):
    root = Path(settings.PRIVATE_FILES_ROOT).resolve()
    path = (root / key).resolve()
    if root not in path.parents:  # a mistake in the code, never reachable from a request
        raise ValueError("A file key must stay inside the storage folder.")
    return path


def key_for_cv(company_id, cv_id):
    return f"cvs/{company_id}/{cv_id}"


def save_file(key, data):
    path = _path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_file(key):
    return _path_for(key).read_bytes()


def delete_file(key):
    """Removes the file; a file that is already gone is fine."""
    _path_for(key).unlink(missing_ok=True)
