"""Items 7 and 8: backups and monitoring."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from backups.models import BackupRun
from platform_settings.service import get_setting

from .results import item, not_ok, ok, owner


def _latest(kind, within):
    return BackupRun.objects.filter(
        kind=kind,
        status=BackupRun.Status.SUCCEEDED,
        finished_at__gte=timezone.now() - within,
    ).exists()


def backups(_context):
    hours = get_setting("backup.late_after_hours")
    days = get_setting("launch.restore_test_max_age_days")
    parts = []
    if _latest(BackupRun.Kind.BACKUP, timedelta(hours=hours)):
        parts.append(ok("A recent backup exists."))
    else:
        parts.append(not_ok(f"No successful backup in the last {hours} hours."))
    if _latest(BackupRun.Kind.RESTORE_TEST, timedelta(days=days)):
        parts.append(ok("The restore test passed recently."))
    else:
        parts.append(not_ok(f"No passed restore test in the last {days} days."))
    parts += [
        owner("The backup encryption key has a copy kept offline."),
        owner("The R2 lifecycle rule for old backups is set."),
    ]
    return item(7, "Backups are made, restorable and protected", parts)


def monitoring(_context):
    parts = []
    for name in ("HEARTBEAT_URL", "BACKUP_HEARTBEAT_URL"):
        if str(getattr(settings, name, "")).startswith("https://"):
            parts.append(ok(f"{name} is set."))
        else:
            parts.append(not_ok(f"{name} is not set to an https address."))
    parts.append(
        owner("The outside uptime check exists and a test alert was received by the owner.")
    )
    return item(8, "Monitoring and alerts", parts)
