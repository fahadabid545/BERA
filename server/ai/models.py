from django.db import models
from django.db.models import Q


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
