from django.db import models
from django.db.models import Q

from core.models import PersonAccount
from core.protected_fields import EncryptedTextField


class AdminUser(PersonAccount):
    """Staff of the platform. Not tied to any company, and never a company user."""

    class Role(models.TextChoices):
        SUPER = "super"
        SUPPORT = "support"

    class Status(models.TextChoices):
        ACTIVE = "active"
        BLOCKED = "blocked"
        REMOVED = "removed"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SUPPORT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    # Two-step verification is required for every admin. The secret is saved when setup starts
    # and only counts once `two_step_enabled` is true. Admins get no recovery codes: another
    # super admin resets a lost device.
    two_step_secret = EncryptedTextField(purpose="adminuser.two_step_secret", default="")
    two_step_enabled = models.BooleanField(default=False)
    two_step_last_step = models.BigIntegerField(null=True)

    class Meta:
        constraints = [
            PersonAccount.email_is_normalised_constraint("adminuser"),
            models.UniqueConstraint(fields=["email"], name="adminuser_email_is_unique"),
            models.CheckConstraint(
                condition=Q(role__in=["super", "support"]), name="adminuser_role_is_known"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "blocked", "removed"]),
                name="adminuser_status_is_known",
            ),
        ]
