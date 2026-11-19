"""Billing emails: a failed payment, and a subscription about to end. Both are required, so
nobody can switch them off."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from companies.models import Company
from core.jobs import logged_job
from emailing.links import build_link
from emailing.rendering import format_moment
from plans.models import Subscription
from plans.subscriptions import owner_of
from platform_settings.service import get_setting

from .kinds import SUBSCRIPTION_ENDING
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
