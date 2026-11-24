from django.db import models
from django.db.models import F, Q

NOTE_COLUMN_LENGTH = 1000
NAME_COLUMN_LENGTH = 200


class DataRequest(models.Model):
    """A company's request to have its data exported or deleted, logged by hand by an admin when
    it arrives (for example by email). The record only tracks the work: it holds no candidate
    content, and carrying the request out is a separate step.

    The company is kept as a plain number and a name, not a link, so the record outlives a company
    whose deletion it asked for (the same way audit entries do)."""

    class Kind(models.TextChoices):
        EXPORT = "export"
        DELETION = "deletion"

    class Status(models.TextChoices):
        OPEN = "open"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"

    company_id = models.BigIntegerField()
    company_name = models.CharField(max_length=200)  # as it was when the request was logged
    kind = models.CharField(max_length=10, choices=Kind.choices)
    requested_by = models.CharField(max_length=NAME_COLUMN_LENGTH)
    received_on = models.DateField()
    # Fixed when the request is logged (received date plus `data_requests.due_days`).
    due_on = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    completed_on = models.DateField(null=True)
    note = models.CharField(max_length=NOTE_COLUMN_LENGTH, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["export", "deletion"]), name="data_request_kind_is_known"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["open", "in_progress", "completed"]),
                name="data_request_status_is_known",
            ),
            models.CheckConstraint(
                condition=Q(due_on__gte=F("received_on")), name="data_request_due_after_received"
            ),
            models.CheckConstraint(
                condition=(Q(status="completed", completed_on__isnull=False))
                | (~Q(status="completed") & Q(completed_on__isnull=True)),
                name="data_request_completed_date_only_when_completed",
            ),
        ]
