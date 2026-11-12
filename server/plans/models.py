from django.db import models
from django.db.models import Q


class Plan(models.Model):
    """A monthly subscription plan that companies buy. Plans are monthly; unused CVs do not
    roll over.

    Everything except the name, the optional description and the PKR price may be empty while
    a plan is being set up, but a plan cannot be active until every number is filled in
    (`plans.service.missing_for_active`)."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        HIDDEN = "hidden"
        ARCHIVED = "archived"

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    price_pkr = models.DecimalField(max_digits=12, decimal_places=2, null=True)  # optional
    cvs_per_month = models.PositiveIntegerField(null=True)
    cvs_per_project = models.PositiveIntegerField(null=True)
    max_projects = models.PositiveIntegerField(null=True)
    max_team_accounts = models.PositiveIntegerField(null=True)  # including the owner
    max_top_n = models.PositiveIntegerField(null=True)
    monthly_ai_token_cap = models.PositiveBigIntegerField(null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HIDDEN)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "hidden", "archived"]),
                name="plan_status_is_known",
            ),
        ]


class PendingPlanChange(models.Model):
    """Changes to a plan with subscribers that wait for their next renewal. Subscribers keep
    what they bought until then. At most one per plan: a newer edit joins the waiting one."""

    plan = models.OneToOneField(Plan, on_delete=models.CASCADE, related_name="pending_change")
    values = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
