import uuid

from django.db import models

from .kinds import ADMIN, COMPANY


class Session(models.Model):
    """One sign-in. Access tokens name their session, so revoking it ends them at once."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        REVOKED = "revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.BigIntegerField()
    kind = models.CharField(max_length=10, choices=[(COMPANY, "Company"), (ADMIN, "Admin")])
    company_id = models.BigIntegerField(null=True, blank=True)
    # Only a hash of the current refresh token is kept, never the token itself.
    refresh_token_hash = models.CharField(max_length=64, unique=True)
    token_family = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    revoke_reason = models.CharField(max_length=40, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "status"]),
            models.Index(fields=["company_id", "status"]),
        ]


class RetiredRefreshToken(models.Model):
    """A refresh token that has been used. Seeing one again means it was copied."""

    token_hash = models.CharField(max_length=64, unique=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="retired_tokens")
