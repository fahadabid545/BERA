from django.db import models
from django.db.models import Q

from core.models import CompanyOwnedModel


class AiModel(models.Model):
    """A model the platform may use, with what it costs. `name` is the provider's model id and
    never changes, because projects pin it by name. Prices are per million tokens; a call is
    priced when it is made, so changing a price never touches an earlier cost record."""

    name = models.CharField(max_length=100, unique=True)
    input_price_per_million = models.DecimalField(max_digits=12, decimal_places=4)
    output_price_per_million = models.DecimalField(max_digits=12, decimal_places=4)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(input_price_per_million__gte=0) & Q(output_price_per_million__gte=0),
                name="aimodel_prices_are_not_negative",
            ),
        ]


class PromptVersion(models.Model):
    """One numbered version of the instructions given to the AI, for reading CVs or for scoring.
    The text of a version never changes after it is created; a change is a new version.
    Projects pin the number they were created with."""

    READING = "reading"
    SCORING = "scoring"
    KINDS = [(READING, "Reading"), (SCORING, "Scoring")]

    kind = models.CharField(max_length=20, choices=KINDS)
    number = models.PositiveIntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "number"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "number"], name="one_prompt_per_number"),
            models.CheckConstraint(
                condition=Q(kind__in=["reading", "scoring"]), name="prompt_kind_is_known"
            ),
        ]


class PromptCounter(models.Model):
    """The last number given for each kind. Numbers are never reused, even after a version is
    deleted, so a number in an old record always means the same text."""

    kind = models.CharField(max_length=20, unique=True)
    last_number = models.PositiveIntegerField(default=0)


class AiCall(CompanyOwnedModel):
    """One call to the AI, written by `ai.client.call_ai` for every call, failed ones included.

    It holds only ids, numbers and the purpose, never what was sent or received, so it holds no
    CV text or contact details. The project, CV and candidate are plain ids, not links: the record
    stays for cost history and billing checks after any of them is deleted. A failed call has
    0 tokens and 0 cost, because the provider reported none. The cost is the one at the prices of
    the moment (see `costs.py`) and is never recalculated."""

    class Purpose(models.TextChoices):
        READING = "reading"
        SCORING = "scoring"
        REQUIREMENT_EXTRACTION = "requirement_extraction"
        PLAYGROUND = "playground"

    class Result(models.TextChoices):
        OK = "ok"
        FAILED = "failed"

    project_id = models.UUIDField(null=True)
    cv_id = models.UUIDField(null=True)
    candidate_id = models.UUIDField(null=True)
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    model = models.CharField(max_length=100)
    prompt_version = models.PositiveIntegerField(null=True)  # none for a prompt with no versions
    tokens_in = models.PositiveBigIntegerField(default=0)
    tokens_out = models.PositiveBigIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    duration_ms = models.PositiveIntegerField()
    result = models.CharField(max_length=10, choices=Result.choices)
    failure = models.CharField(max_length=100, blank=True)  # a short reason when it failed
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "created_at"], name="aicall_company_time"),
            models.Index(fields=["created_at"], name="aicall_time"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    purpose__in=["reading", "scoring", "requirement_extraction", "playground"]
                ),
                name="aicall_purpose_is_known",
            ),
            models.CheckConstraint(
                condition=Q(result="ok", failure="") | Q(result="failed"),
                name="aicall_failure_only_when_failed",
            ),
        ]
