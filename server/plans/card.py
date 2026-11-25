"""Updating the card, on the payment provider's own page.

Card details are typed there and never reach this server or our database; what is shown (brand,
last four digits, expiry) is read from the provider each time. The way back carries only a marker:
the result is always read from the provider (the default card changed) or from its own notice,
never from the return address. A card update never restores access by itself: for a Past due
company the open invoice is asked to be paid again, and only the provider's paid notice (BERA-165)
makes the company Active."""

from django.db import transaction
from django.utils import timezone

from audit.security import record_security_event
from companies.models import Company
from core.errors import AppError

from . import stripe_client
from .renewal import billed_subscription, portal_address
from .subscriptions import State, effective_state, get_subscription

CARD_RETURN_PATH = "/company/billing?card=returned"
UPDATED, NOT_CHANGED, CHECKING, NOTHING_ASKED = "updated", "not_changed", "checking", "none"


def _lock(company_id):
    Company.objects.select_for_update().get(pk=company_id)  # one billing change at a time


def card_on_file(company_id):
    """What the owner may see of the card; None when there is no card."""
    subscription = billed_subscription(company_id)
    card = stripe_client.default_card(
        subscription.stripe_customer_id, subscription.stripe_subscription_id
    )
    if card is None:
        return None
    return {name: value for name, value in card.items() if name != "payment_method_id"}


def open_card_update(company_id, *, by):
    """The address of the provider's card screen. The card that is the default now is remembered
    (by its id) so the result can be told apart later."""
    subscription = billed_subscription(company_id)
    before = stripe_client.default_card(
        subscription.stripe_customer_id, subscription.stripe_subscription_id
    )
    url = portal_address(
        subscription, return_path=CARD_RETURN_PATH, flow=stripe_client.CARD_UPDATE_FLOW
    )
    with transaction.atomic():
        _lock(company_id)
        type(subscription).objects.filter(pk=subscription.pk).update(
            card_update_started_at=timezone.now(),
            card_update_started_with=before["payment_method_id"] if before else "",
            card_update_outcome="",
        )
        record_security_event(
            "security.card_update_opened",
            actor=by,
            target=Company.objects.get(pk=company_id),
            details={"state": effective_state(subscription, timezone.now())},
        )
    return url


def _changed(subscription):
    """Whether the card changed since the page was opened: the provider's own notice if it has
    arrived, otherwise the provider's current default card. None when that cannot be read."""
    if (
        subscription.card_changed_at
        and subscription.card_changed_at >= subscription.card_update_started_at
    ):
        return True
    try:
        now = stripe_client.default_card(
            subscription.stripe_customer_id, subscription.stripe_subscription_id
        )
    except AppError:
        return None
    return (now["payment_method_id"] if now else "") != subscription.card_update_started_with


def check_card_update(company_id, *, by):
    """The result of the last "Update card" visit, saved once it is known. Safe to ask again."""
    with transaction.atomic():
        _lock(company_id)
        subscription = get_subscription(company_id)
        if not subscription.card_update_started_at:
            return NOTHING_ASKED
        if subscription.card_update_outcome:
            return subscription.card_update_outcome
        changed = _changed(subscription)
        if changed is None:
            return CHECKING
        outcome = UPDATED if changed else NOT_CHANGED
        type(subscription).objects.filter(pk=subscription.pk).update(card_update_outcome=outcome)
        record_security_event(
            "security.card_update_result",
            actor=by,
            target=Company.objects.get(pk=company_id),
            details={"result": outcome},
        )
        if outcome == UPDATED and effective_state(subscription) == State.PAST_DUE:
            stripe_client.retry_open_invoice(subscription.stripe_subscription_id)
    return outcome
