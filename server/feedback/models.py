from django.db import models
from django.db.models import Q

from core.models import CompanyOwnedModel
from core.protected_fields import EncryptedTextField

# The column sizes; the lengths people may actually write are platform settings that may never be
# set above these.
PAGE_COLUMN_LENGTH = 200
NOTE_COLUMN_LENGTH = 1000


class Feedback(CompanyOwnedModel):
    """What a signed-in person sent through "Send feedback". The message is free text from a
    company, so it is company data: stored encrypted, shown only to the company's own people and
    to admins, removed with the company, and never written to a log or an email."""

    class Kind(models.TextChoices):
        BUG = "bug"
        IDEA = "idea"
        QUESTION = "question"

    class Status(models.TextChoices):
        NEW = "new"
        REVIEWING = "reviewing"
        FIXED = "fixed"
        WONT_FIX = "wont_fix"

    user = models.ForeignKey("companies.CompanyUser", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    message = EncryptedTextField(purpose="feedback.message")
    page = models.CharField(max_length=PAGE_COLUMN_LENGTH)  # the address it was sent from
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    # Written by an admin, for admins. Never shown to the company.
    note = models.CharField(max_length=NOTE_COLUMN_LENGTH, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "-created_at"], name="feedback_status_newest")]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["bug", "idea", "question"]), name="feedback_kind_is_known"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["new", "reviewing", "fixed", "wont_fix"]),
                name="feedback_status_is_known",
            ),
        ]
