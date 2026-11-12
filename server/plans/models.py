from django.db import models
from django.db.models import Q

from core.models import CompanyOwnedModel


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


class Subscription(CompanyOwnedModel):
    """A company's one subscription. Only payment events and admin actions change its state,
    through `plans.subscriptions`; no route lets a company change it. One row per company is
    what makes two active subscriptions at once impossible.

    The stored state can lag behind the dates (a grace period or a paid period that ended with
    no job run yet); `plans.subscriptions.effective_state` is what access is decided on."""

    class State(models.TextChoices):
        NO_PLAN = "no_plan"
        ACTIVE = "active"
        PAST_DUE = "past_due"
        CANCELLED = "cancelled"  # still active until the period ends
        EXPIRED = "expired"
        GRANTED_FREE = "granted_free"

    plan = models.ForeignKey(Plan, null=True, on_delete=models.PROTECT, related_name="+")
    state = models.CharField(max_length=20, choices=State.choices, default=State.NO_PLAN)
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    renewal = models.BooleanField(default=False)
    # When payment first failed; the grace period counts from here.
    past_due_since = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company"], name="one_subscription_per_company"),
            models.CheckConstraint(
                condition=Q(
                    state__in=[
                        "no_plan",
                        "active",
                        "past_due",
                        "cancelled",
                        "expired",
                        "granted_free",
                    ]
                ),
                name="subscription_state_is_known",
            ),
        ]
