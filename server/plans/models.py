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
    # The payment provider's ids, kept for the webhook and renewal tickets. Empty for a company
    # that never paid by card (free grants, no plan). Not secrets, but never shown to the company.
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    # When the provider created the newest paid-invoice event applied here, so a failure that is
    # older than a later payment (delivered late) cannot make the company past due again.
    provider_paid_at = models.DateTimeField(null=True)
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


class LimitOverride(CompanyOwnedModel):
    """A limit set for one company, replacing its plan's value. Admin limit and subscription
    controls creates and removes these; everything reads limits through `plans.limits`."""

    name = models.CharField(max_length=40)
    value = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="one_override_per_limit"),
        ]


class PaymentEvent(CompanyOwnedModel):
    """One payment, refund or failed payment, as the payment provider reported it. The provider's
    own event id is unique, so an event that is delivered twice is one record. Written only by
    `plans.payments.record_event`, the one function every payment source must use (the provider's
    webhook included): there is no second payments table. Amounts are in the smallest unit of the
    currency (cents), never rounded; the record is never changed after it is written."""

    class Kind(models.TextChoices):
        PAYMENT = "payment"
        REFUND = "refund"
        FAILURE = "failure"

    provider_event_id = models.CharField(max_length=255, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)  # ISO code, upper case
    reason = models.CharField(max_length=200, blank=True)  # why a payment failed, in words
    # The plan the company was on when it paid; empty for older records and for events with none.
    plan = models.ForeignKey(Plan, null=True, on_delete=models.PROTECT, related_name="+")
    occurred_at = models.DateTimeField()  # when the provider says it happened
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["occurred_at"], name="paymentevent_time"),
            models.Index(fields=["company", "occurred_at"], name="paymentevent_company_time"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["payment", "refund", "failure"]),
                name="paymentevent_kind_is_known",
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=r"^[A-Z]{3}$"), name="paymentevent_currency_is_iso"
            ),
        ]


class CheckoutAttempt(CompanyOwnedModel):
    """One visit to the payment provider's secure page. It makes a double click safe (an open
    attempt for the same plan is reused) and activation once-only (a paid attempt is marked
    `activated` in the same step that activates the subscription). Holds no card data."""

    class Status(models.TextChoices):
        OPEN = "open"
        ACTIVATED = "activated"
        REPLACED = "replaced"  # the company chose another plan; the old page was closed

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # What the page asked for, kept so a paid session is only trusted if it matches.
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    payment_page_url = models.URLField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stripe_session_id"],
                condition=~Q(stripe_session_id=""),
                name="one_attempt_per_provider_session",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["open", "activated", "replaced"]),
                name="checkout_status_is_known",
            ),
        ]
