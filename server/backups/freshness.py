"""The hourly check that a backup was made recently. It runs on the server itself, so it
catches a backup job that stopped or never started; a dead server is watched from outside
(BERA-180)."""

from datetime import timedelta

from django.utils import timezone

from audit.security import record_security_event
from platform_settings.service import get_setting

from .models import BackupRun


def check_backup_is_recent():
    """True when the latest successful backup is recent enough; otherwise alerts and is False."""
    limit = timezone.now() - timedelta(hours=get_setting("backup.late_after_hours"))
    recent = BackupRun.objects.filter(
        kind=BackupRun.Kind.BACKUP, status=BackupRun.Status.SUCCEEDED, finished_at__gte=limit
    ).exists()
    if not recent:
        record_security_event("security.backup_late", details={"reason": "late"})
    return recent
