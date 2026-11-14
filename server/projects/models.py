from django.db import models
from django.db.models import Q

from core.models import CompanyOwnedModel
from platform_settings.definitions import DEFINITIONS


class Project(CompanyOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ARCHIVED = "archived"

    """One job opening. Lengths are limited by platform settings when it is written, so the
    columns are plain text and a changed limit needs no migration.

    The reading and scoring models and the two prompt versions are the defaults at the moment of
    creation. They change only by an admin action (a replacement for a disabled model, or moving
    the project to another prompt version), so a project is always read the way it was
    first set up."""

    title = models.TextField()
    job_description = models.TextField()
    reading_model = models.CharField(max_length=100)
    scoring_model = models.CharField(
        max_length=100, default=DEFINITIONS["ai.scoring_model"].default
    )
    reading_prompt_version = models.PositiveIntegerField(
        default=DEFINITIONS["ai.reading_prompt_version"].default
    )
    scoring_prompt_version = models.PositiveIntegerField(
        default=DEFINITIONS["ai.scoring_prompt_version"].default
    )
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


class Requirement(CompanyOwnedModel):
    """One thing a project asks for. The order is the order the person arranged them in.
    Lengths and the weight range are limited by platform settings when written."""

    class Kind(models.TextChoices):
        MUST = "must"
        NICE = "nice"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="requirements")
    position = models.PositiveIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    text = models.TextField()
    weight = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["must", "nice"]), name="requirement_kind_is_known"
            ),
            models.CheckConstraint(condition=Q(weight__gte=1), name="requirement_weight_positive"),
        ]


class ProjectScoringSettings(CompanyOwnedModel):
    """How one project's scores are calculated. A project with no row follows the scoring
    defaults (platform settings today, the company's own later). The weights always total 100;
    the percent limits and the plan's top-N cap are checked in `scoring_settings.py`."""

    project = models.OneToOneField(Project, on_delete=models.PROTECT, related_name="scoring")
    must_weight_percent = models.PositiveSmallIntegerField()
    nice_weight_percent = models.PositiveSmallIntegerField()
    recommendation_threshold = models.PositiveSmallIntegerField()
    top_n = models.PositiveIntegerField()
    cap_on_missing_must_have = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(must_weight_percent__lte=100, nice_weight_percent__lte=100)
                & Q(must_weight_percent=100 - models.F("nice_weight_percent")),
                name="scoring_weights_total_100",
            ),
            models.CheckConstraint(
                condition=Q(recommendation_threshold__lte=100),
                name="scoring_threshold_is_a_percent",
            ),
            models.CheckConstraint(condition=Q(top_n__gte=1), name="scoring_top_n_is_positive"),
        ]


class ProjectFactorSettings(CompanyOwnedModel):
    """Which extra scoring factors a project uses and how much each counts, plus what the job
    expects (the three optional fields the experience, education and seniority factors compare a
    CV with). A project with no row has every factor switched off. Checked in
    `factor_settings.py`; `factors` holds `{factor: {"enabled": bool, "weight": 0-100}}`."""

    project = models.OneToOneField(
        Project, on_delete=models.PROTECT, related_name="factor_settings"
    )
    required_years = models.PositiveSmallIntegerField(null=True)
    required_education = models.CharField(max_length=20, null=True)
    seniority = models.CharField(max_length=20, null=True)
    factors = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
