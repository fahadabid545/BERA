"""Talking to PostgreSQL's own dump and restore programs. Passwords travel in environment
variables, never in a command line (which other accounts on the server can read)."""

import logging
import os
import subprocess
from urllib.parse import parse_qs, unquote, urlsplit

from .errors import BackupFailure

logger = logging.getLogger(__name__)


def connection_environment(url, database=None):
    parts = urlsplit(url)
    return {
        "PGHOST": parts.hostname or "",
        "PGPORT": str(parts.port or 5432),
        "PGUSER": unquote(parts.username or ""),
        "PGPASSWORD": unquote(parts.password or ""),
        "PGDATABASE": database or parts.path.lstrip("/"),
        "PGSSLMODE": parse_qs(parts.query).get("sslmode", ["prefer"])[-1],
    }


class DumpStream:
    """The output of `pg_dump`, read like a file. Reading to the end fails if pg_dump failed, so
    an incomplete dump can never look like a finished one."""

    def __init__(self, url):
        self._process = subprocess.Popen(  # noqa: S603 - fixed program, no user input
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges"],
            env={**os.environ, **connection_environment(url)},
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def read(self, size=-1):
        data = self._process.stdout.read(size)
        if not data:
            code = self._process.wait()
            if code != 0:
                logger.error("pg_dump ended with exit code %s.", code)
                raise BackupFailure("database_dump")
        return data

    def close(self):
        if self._process.poll() is None:
            self._process.kill()
        self._process.stdout.close()
        self._process.wait()


def restore_into(url, database, source):
    """Feeds `source` (a file-like object) to pg_restore, for the named throwaway database."""
    process = subprocess.Popen(  # noqa: S603 - fixed program, no user input
        ["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", database],
        env={**os.environ, **connection_environment(url, database)},
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        while chunk := source.read(1024 * 1024):
            process.stdin.write(chunk)
        process.stdin.close()
    except BrokenPipeError:
        pass  # pg_restore stopped early; its exit code below says why
    except BaseException:
        process.kill()
        process.wait()
        raise
    code = process.wait()
    if code != 0:
        logger.error("pg_restore ended with exit code %s.", code)
        raise BackupFailure("restore")
