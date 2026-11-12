from django.db import models

from core.errors import ConfigurationError

PERMANENT = "Audit entries are permanent: they cannot be changed or deleted."


class PermanentQuerySet(models.QuerySet):
    """Rows can be added and read, never changed or removed, whatever the caller tries."""

    def update(self, **kwargs):
        raise ConfigurationError(PERMANENT)

    def delete(self):
        raise ConfigurationError(PERMANENT)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ConfigurationError(PERMANENT)

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ConfigurationError(PERMANENT)


class AuditEvent(models.Model):
    """One thing that happened: who did what, when, to which company or person, and why.

    People and companies are kept as plain numbers, not links, so an entry outlives the
    account it is about. Nothing here holds a password, a token or CV text (see `record`).
    The database refuses changes too (migration 0001), not only this code."""

    class ActorKind(models.TextChoices):
        COMPANY = "company"
        ADMIN = "admin"
        NONE = "none"  # a visitor who is not signed in, or the system itself

    kind = models.CharField(max_length=60)
    actor_kind = models.CharField(max_length=10, choices=ActorKind.choices)
    actor_id = models.BigIntegerField(null=True)
    company_id = models.BigIntegerField(null=True)
    target_kind = models.CharField(max_length=30, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    reason = models.TextField(blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PermanentQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["company_id", "created_at"]),
            models.Index(fields=["actor_kind", "actor_id", "created_at"]),
            models.Index(fields=["kind", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ConfigurationError(PERMANENT)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ConfigurationError(PERMANENT)
