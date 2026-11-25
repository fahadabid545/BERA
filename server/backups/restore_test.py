"""The weekly proof that a backup can really be restored: the newest backup is read from the
storage, decrypted with the key as configured now, restored into a throwaway database and
checked, and the throwaway database is deleted again whatever happens. It never touches the
real database, nor staging's."""

import logging
import secrets

import psycopg
from django.conf import settings
from django.utils import timezone
from psycopg import sql

from .database import connection_environment, restore_into
from .errors import BackupFailure
from .format import DecryptingReader
from .keys import key_ring
from .models import BackupRun
from .reporting import fail_run, record_run
from .store import get_store

logger = logging.getLogger(__name__)


def _connect(url, database=None):
    environment = connection_environment(url, database)
    return psycopg.connect(
        host=environment["PGHOST"],
        port=environment["PGPORT"],
        user=environment["PGUSER"],
        password=environment["PGPASSWORD"],
        dbname=environment["PGDATABASE"],
        sslmode=environment["PGSSLMODE"],
        autocommit=True,
    )


def _check_restored(url, database):
    """The restored copy has tables, and the record of applied migrations is not empty."""
    with _connect(url, database) as connection:
        tables = connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchone()[0]
        migrations = connection.execute("SELECT count(*) FROM django_migrations").fetchone()[0]
    if not tables or not migrations:
        raise BackupFailure("verification")


def _drop(url, database):
    try:
        with _connect(url) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )
    except psycopg.Error:
        raise BackupFailure("cleanup") from None


def _restore_and_check(store, name, keys):
    url = settings.RESTORE_TEST_DATABASE_URL
    database = f"bera_restore_test_{secrets.token_hex(6)}"
    try:
        with _connect(url) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    except psycopg.Error:
        raise BackupFailure("restore") from None
    problem = None
    try:
        source = store.open(name)
        try:
            restore_into(url, database, DecryptingReader(source, keys))
        finally:
            source.close()
        try:
            _check_restored(url, database)
        except psycopg.Error:
            raise BackupFailure("verification") from None
    except BackupFailure as failure:
        problem = failure
    finally:
        try:
            _drop(url, database)
        except BackupFailure as failure:
            problem = problem or failure
    if problem:
        raise problem


def verify_restore():
    """Returns the run. A failure is recorded, announced and raised as BackupFailure."""
    started = timezone.now()
    name = ""
    try:
        _, keys = key_ring()
        store = get_store()
        newest = max(store.list(), key=lambda item: item.modified, default=None)
        if newest is None:
            raise BackupFailure("no_backup")
        name = newest.name
        _restore_and_check(store, name, keys)
    except BackupFailure as failure:
        fail_run(BackupRun.Kind.RESTORE_TEST, started, failure.kind, object_name=name)
        raise
    except Exception as error:
        logger.error("The restore test stopped with %s.", type(error).__name__)
        fail_run(BackupRun.Kind.RESTORE_TEST, started, "unexpected", object_name=name)
        raise BackupFailure("unexpected") from None
    return record_run(BackupRun.Kind.RESTORE_TEST, started, object_name=name)
