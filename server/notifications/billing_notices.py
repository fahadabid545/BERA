"""Billing emails: a failed payment, a subscription about to renew, and one about to end. All
are required, so nobody can switch them off."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from companies.models import Company
from core.jobs import logged_job
from emailing.links import build_link
from emailing.rendering import format_moment
from plans.models import Subscription
from plans.pricing import charge_price
from plans.subscriptions import owner_of
from platform_settings.service import get_setting

from .kinds import SUBSCRIPTION_ENDING, SUBSCRIPTION_RENEWING
from .service import notify

State = Subscription.State
BILLING_PATH = "/company/billing"


def _ending_soon(now, days):
    """Subscriptions that stop at their period end: cancelled, free for a time, or active
    without renewal. A renewing one is not ending."""
    ends_without_renewal = Q(state__in=[State.CANCELLED, State.GRANTED_FREE]) | Q(
        state=State.ACTIVE, renewal=False
    )
    return Subscription.objects.filter(
        ends_without_renewal,
        company__status=Company.Status.ACTIVE,
        period_end__gt=now,
        period_end__lte=now + timedelta(days=days),
    )


@logged_job
def send_ending_notices():
    """Daily job: emails the owner once, `notifications.subscription_ending_days` before the
    subscription ends. Returns how many emails were sent."""
    now = timezone.now()
    sent = 0
    for subscription in _ending_soon(now, get_setting("notifications.subscription_ending_days")):
        owner = owner_of(subscription.company_id)
        if owner is None:
            continue
        sent += notify(
            subscription.company_id,
            SUBSCRIPTION_ENDING,
            subscription.period_end.isoformat(),
            [owner],
            "subscription_ending",
            when=format_moment(subscription.period_end),
            link=build_link(BILLING_PATH),
        )
    return sent


def _renewing_soon(now, days):
    """Subscriptions that charge the card at their period end."""
    return Subscription.objects.filter(
        state=State.ACTIVE,
        renewal=True,
        company__status=Company.Status.ACTIVE,
        period_end__gt=now,
        period_end__lte=now + timedelta(days=days),
    ).exclude(stripe_subscription_id="")


def _next_charge(subscription):
    """The plan the next invoice is for: a waiting downgrade already has its lower price."""
    waiting = subscription.pending_plan if subscription.pending_change == "downgrade" else None
    plan = waiting or subscription.plan
    price = charge_price(plan)
    return plan, f"{price.currency} {price.amount:,.2f}"


@logged_job
def send_renewal_notices():
    """Daily job: emails the owner once, `notifications.subscription_ending_days` before the card
    is charged for the next month, with the plan, the date and the amount. Returns how many
    emails were sent."""
    now = timezone.now()
    sent = 0
    for subscription in _renewing_soon(now, get_setting("notifications.subscription_ending_days")):
        owner = owner_of(subscription.company_id)
        if owner is None or subscription.plan is None:
            continue
        plan, amount = _next_charge(subscription)
        sent += notify(
            subscription.company_id,
            SUBSCRIPTION_RENEWING,
            subscription.period_end.isoformat(),
            [owner],
            "subscription_renewing",
            plan=plan.name,
            when=format_moment(subscription.period_end),
            amount=amount,
            link=build_link(BILLING_PATH),
        )
    return sent
