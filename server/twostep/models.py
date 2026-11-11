from django.db import models


class RecoveryCode(models.Model):
    """A one-time code that replaces the authenticator app code. Only a keyed hash is kept, so
    nobody can read a code back; the person sees them once, when they are made."""

    user = models.ForeignKey(
        "companies.CompanyUser", on_delete=models.CASCADE, related_name="recovery_codes"
    )
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "code_hash"], name="recoverycode_is_unique")
        ]
