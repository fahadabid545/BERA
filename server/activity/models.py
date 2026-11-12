from django.db import models

from core.models import CompanyOwnedModel


class ActivityEntry(CompanyOwnedModel):
    """One thing a company's team did, for the company's own Activity tab.

    Kept apart from project data and from the admin audit log (`audit`). The person is kept as
    a number and the name they had at the time, not a link, so an entry stays readable after
    the member is removed. Details are short facts, never the content of a CV."""

    kind = models.CharField(max_length=30)
    actor_id = models.BigIntegerField(null=True)
    actor_name = models.CharField(max_length=200, blank=True)
    target_kind = models.CharField(max_length=30, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["company", "-created_at"])]
