from django.db import models
from django.db.models import Q

from core.models import CompanyOwnedModel


class Project(CompanyOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ARCHIVED = "archived"

    """One job opening. Lengths are limited by platform settings when it is written, so the
    columns are plain text and a changed limit needs no migration.

    The reading model and prompt version are the defaults at the moment of creation and never
    change afterwards, so a project is always read the way it was first set up."""

    title = models.TextField()
    job_description = models.TextField()
    reading_model = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        "companies.CompanyUser", on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "archived"]), name="project_status_is_known"
            ),
        ]
