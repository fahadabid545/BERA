from django.db import models


class BackupRun(models.Model):
    """One backup or one restore test. Holds no data from the database: only when it ran, how it
    ended and, for a failure, the kind of failure (see errors.py)."""

    class Kind(models.TextChoices):
        BACKUP = "backup"
        RESTORE_TEST = "restore_test"

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded"
        FAILED = "failed"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    object_name = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    encryption_key_id = models.CharField(max_length=32, blank=True)
    failure_kind = models.CharField(max_length=30, blank=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "status", "-finished_at"])]
