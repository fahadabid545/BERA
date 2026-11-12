from django.db import models
from django.db.models import Q

from core.models import CompanyOwnedModel


class UsagePeriod(CompanyOwnedModel):
    """One billing period of one company. Kept for ever, so history per period is available."""

    start = models.DateTimeField()
    end = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "start"], name="one_usage_period_start"),
            models.CheckConstraint(
                condition=Q(end__gt=models.F("start")), name="period_has_length"
            ),
        ]


class UsageCounter(CompanyOwnedModel):
    """What one project (or work with no project) used in one period. The company's total is
    the sum of its projects' counters."""

    period = models.ForeignKey(UsagePeriod, on_delete=models.PROTECT, related_name="counters")
    project_id = models.UUIDField(null=True)
    cvs_scored = models.PositiveIntegerField(default=0)
    tokens_in = models.PositiveBigIntegerField(default=0)
    tokens_out = models.PositiveBigIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=6, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["period", "project_id"],
                name="one_counter_per_project_and_period",
                nulls_distinct=False,
            ),
        ]


class CvUsage(CompanyOwnedModel):
    """The ledger entry of one accepted CV. It fixes the period the CV counts in (the one it
    was accepted in) and makes sure it is counted once, however many times it is scored."""

    class Status(models.TextChoices):
        PENDING = "pending"  # accepted, waiting or being read and scored
        SCORED = "scored"  # counted
        FAILED = "failed"  # not counted; its allowance is given back

    cv_id = models.UUIDField(unique=True)
    project_id = models.UUIDField(null=True)
    period = models.ForeignKey(UsagePeriod, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    accepted_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "scored", "failed"]),
                name="cvusage_status_is_known",
            ),
        ]
