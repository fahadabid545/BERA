"""The daily backup: copy the database, encrypt it as it streams, keep it in the backup storage,
then remove backups that are past their retention.

Old backups are removed only after this run's backup was saved and its size checked, and the
newest few are never removed, so a failing backup can never lead to having none.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from monitoring.heartbeat import ping
from platform_settings.service import get_setting

from .database import DumpStream
from .errors import BackupFailure
from .format import EncryptingReader
from .keys import key_ring
from .models import BackupRun
from .reporting import announce_problem, fail_run, record_run
from .store import get_store, object_name

logger = logging.getLogger(__name__)


def _copy_to_storage(store, name, key_id, key_text):
    dump = DumpStream(settings.BACKUP_DATABASE_URL)
    try:
        encrypted = EncryptingReader(dump, key_id, key_text)
        store.save(name, encrypted)
    finally:
        dump.close()
    if store.size(name) != encrypted.bytes_read:
        store.delete(name)
        raise BackupFailure("upload")
    return encrypted.bytes_read


def remove_expired(store, now):
    """Deletes backups older than the retention, never the newest `backup.minimum_kept`."""
    cutoff = now - timedelta(days=get_setting("backup.retention_days"))
    newest_first = sorted(store.list(), key=lambda item: item.modified, reverse=True)
    for item in newest_first[get_setting("backup.minimum_kept") :]:
        if item.modified < cutoff:
            store.delete(item.name)


def run_backup():
    """Returns the run. A failure is recorded, announced and raised as BackupFailure."""
    started = timezone.now()
    name = object_name(started)
    try:
        key_id, keys = key_ring()
        store = get_store()
        size = _copy_to_storage(store, name, key_id, keys[key_id])
    except BackupFailure as failure:
        fail_run(BackupRun.Kind.BACKUP, started, failure.kind)
        raise
    except Exception as error:
        # Only the kind of error is logged: the message could hold a database address.
        logger.error("The backup stopped with %s.", type(error).__name__)
        fail_run(BackupRun.Kind.BACKUP, started, "unexpected")
        raise BackupFailure("unexpected") from None
    run = record_run(
        BackupRun.Kind.BACKUP,
        started,
        object_name=name,
        size_bytes=size,
        encryption_key_id=key_id,
    )
    # The outside service raises the alarm when these pings stop (BERA-180): a backup that did not
    # run, or did not succeed, sends none.
    ping(settings.BACKUP_HEARTBEAT_URL)
    try:
        remove_expired(store, started)
    except Exception as error:
        logger.error("Removing old backups stopped with %s.", type(error).__name__)
        announce_problem("security.backup_failed", "pruning")
    return run
