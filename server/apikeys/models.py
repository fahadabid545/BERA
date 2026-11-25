from django.db import models

from core.models import CompanyOwnedModel

NAME_COLUMN_LENGTH = 100
IDEMPOTENCY_KEY_LENGTH = 64


class ApiKey(CompanyOwnedModel):
    """One key a company's owner made for the API. The key itself is shown once and never kept:
    only its SHA-256 hash is stored (the key is long and random, so a plain hash is enough and a
    lookup by hash is exact). `last_four` only helps the owner tell keys apart."""

    created_by = models.ForeignKey(
        "companies.CompanyUser", on_delete=models.PROTECT, related_name="+"
    )
    name = models.CharField(max_length=NAME_COLUMN_LENGTH)
    key_hash = models.CharField(max_length=64, unique=True)
    last_four = models.CharField(max_length=4)
    scopes = models.JSONField(default=list)
    expires_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    last_used_at = models.DateTimeField(null=True)
    request_count = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "revoked_at"], name="apikey_company_live")]


class ApiIdempotency(CompanyOwnedModel):
    """A repeated upload request is answered with the first answer and never processed twice.
    `response` stays empty while the first request is still running."""

    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name="+")
    idempotency_key = models.CharField(max_length=IDEMPOTENCY_KEY_LENGTH)
    fingerprint = models.CharField(max_length=64)  # of the project and the files sent
    response = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["api_key", "idempotency_key"], name="one_answer_per_idempotency_key"
            )
        ]
