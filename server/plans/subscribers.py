"""How many companies are subscribed to a plan: those whose subscription holds it and still
gives access (an expired or plan-less one is not a subscriber)."""

from .models import Subscription

SUBSCRIBED_STATES = (
    Subscription.State.ACTIVE,
    Subscription.State.PAST_DUE,
    Subscription.State.CANCELLED,
    Subscription.State.GRANTED_FREE,
)


def subscriber_count(plan):
    return Subscription.objects.filter(plan=plan, state__in=SUBSCRIBED_STATES).count()
