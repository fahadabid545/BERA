from django.db import models
from django.db.models import Q

from core.models import PersonAccount


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
    two_step_set = models.BooleanField(default=False)

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
