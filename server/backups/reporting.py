"""Writing down how a run ended, and telling the super admins when it did not go well. Only the
kind of failure is ever recorded or sent (see errors.py)."""

import logging

from django.utils import timezone

from audit.security import record_security_event

from .errors import DESCRIPTIONS
from .models import BackupRun

logger = logging.getLogger(__name__)
EVENT_FOR_RUN = {
    BackupRun.Kind.BACKUP: "security.backup_failed",
    BackupRun.Kind.RESTORE_TEST: "security.restore_test_failed",
}


def record_run(kind, started_at, *, failure_kind="", **facts):
    return BackupRun.objects.create(
        kind=kind,
        status=BackupRun.Status.FAILED if failure_kind else BackupRun.Status.SUCCEEDED,
        started_at=started_at,
        finished_at=timezone.now(),
        failure_kind=failure_kind,
        **facts,
    )


def announce_problem(event, failure_kind):
    """The audit log entry and the email, once per kind per cooldown."""
    record_security_event(
        event, details={"reason": failure_kind}, note=f"The reason: {DESCRIPTIONS[failure_kind]}."
    )


def fail_run(kind, started_at, failure_kind, **facts):
    record_run(kind, started_at, failure_kind=failure_kind, **facts)
    announce_problem(EVENT_FOR_RUN[kind], failure_kind)
