from django.db import models

from core.models import CompanyOwnedModel


class Project(CompanyOwnedModel):
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
    created_at = models.DateTimeField(auto_now_add=True)
