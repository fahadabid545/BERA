"""What each verified notification from the payment provider (Stripe) changes. The webhook view
verifies the signature first; nothing here ever sees an unverified body.

Every handler is safe to repeat and safe out of order: a payment record is made once per Stripe
event id, and the first thing a handler does is write it, so a repeated event stops there and
changes nothing else. State changes follow rules that a stale event cannot satisfy (a period must
end later than the current one; a failure older than a later payment is ignored).

Handled: `invoice.paid` (record the payment and move to the invoice's own period; Stripe's dates,
never ours), `invoice.payment_failed` (record it and make the company Past due, which emails the
owner) and `customer.subscription.deleted` (renewal stops; access runs to the period end). Other
types are acknowledged and ignored."""

import logging
from datetime import UTC, datetime

from django.db import transaction
from django.db.models import Q

from companies.models import Company

from .invoices import store_invoice
from .models import CheckoutAttempt, Plan
from .payments import record_event
from .plan_change import warn_over_limits
from .subscriptions import State, activate, cancel, effective_state, get_subscription, mark_past_due

logger = logging.getLogger(__name__)

HANDLED, DUPLICATE, UNMATCHED, IGNORED = "handled", "duplicate", "unmatched", "ignored"
FIRST_INVOICE = "subscription_create"
PLAN_CHANGE_INVOICE = "subscription_update"  # the charge for the rest of the period on an upgrade
FAILURE_REASON = "Payment attempt {attempt} failed."


def _at(timestamp):
    return datetime.fromtimestamp(int(timestamp), UTC)


def _dig(value, *path):
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _subscription_id(invoice):
    # Newer API versions moved the subscription under `parent`; both are read.
    found = invoice.get("subscription") or _dig(
        invoice, "parent", "subscription_details", "subscription"
    )
    return str(_dig(found, "id") or found or "")


def _metadata(invoice):
    return (
        _dig(invoice, "subscription_details", "metadata")
        or _dig(invoice, "parent", "subscription_details", "metadata")
        or {}
    )


def _company_for(provider_subscription_id, metadata):
    """The company a subscription belongs to: by the id we saved, otherwise by the ids we put on
    the subscription when it was made (the first invoice can arrive before the buyer is back)."""
    from .models import Subscription

    known = Subscription.objects.filter(stripe_subscription_id=provider_subscription_id).first()
    if provider_subscription_id and known:
        return known.company_id
    try:
        company_id = int(metadata.get("company_id"))
    except (TypeError, ValueError):
        return None
    return company_id if Company.objects.filter(pk=company_id).exists() else None


def _lock(company_id):
    Company.objects.select_for_update().get(pk=company_id)  # one change at a time per company


def _unmatched(event):
    # Ids only: no body, no personal data.
    logger.warning("Payment notification %s (%s) matches no company.", event["id"], event["type"])
    return UNMATCHED


def _paid_period(invoice):
    lines = _dig(invoice, "lines", "data") or []
    period = lines[0].get("period") if lines else None
    if not period or not period.get("start") or not period.get("end"):
        return None
    return _at(period["start"]), _at(period["end"])


def _plan_for(subscription, metadata, invoice):
    """The plan an invoice pays for. Only the first invoice names it in its own metadata (the
    plan bought at checkout); later ones are the company's current plan, or the plan its waiting
    change moves it to: an upgrade's own invoice, or the first renewal after a downgrade."""
    Change = type(subscription).Change
    reason = invoice.get("billing_reason")
    if reason != FIRST_INVOICE:
        waiting_for = {PLAN_CHANGE_INVOICE: Change.UPGRADE}.get(reason, Change.DOWNGRADE)
        if subscription.pending_change == waiting_for and subscription.pending_plan:
            return subscription.pending_plan
        if subscription.plan:
            return subscription.plan
    plan_id = str(metadata.get("plan_id", ""))
    return (
        Plan.objects.filter(pk=plan_id).first() if plan_id.isdigit() else None
    ) or subscription.plan


def handle_invoice_paid(event):
    invoice = event["data"]["object"]
    provider_subscription_id, metadata = _subscription_id(invoice), _metadata(invoice)
    company_id = _company_for(provider_subscription_id, metadata)
    if company_id is None:
        return _unmatched(event)
    paid_at = _at(event["created"])
    with transaction.atomic():
        _lock(company_id)
        subscription = get_subscription(company_id)
        plan = _plan_for(subscription, metadata, invoice)
        _, created = record_event(
            provider_event_id=event["id"],
            company_id=company_id,
            kind="payment",
            amount_minor=invoice["amount_paid"],
            currency=invoice["currency"],
            occurred_at=paid_at,
            plan_id=plan.pk if plan else None,
        )
        if not created:
            return DUPLICATE
        _apply_paid_period(invoice, subscription, plan, provider_subscription_id, paid_at)
        store_invoice(company_id, plan, invoice, issued_at=paid_at, period=_paid_period(invoice))
    return HANDLED


def _apply_paid_period(invoice, subscription, plan, provider_subscription_id, paid_at):
    """Moves the subscription to the period the paid invoice covers, when that is newer."""
    period = _paid_period(invoice)
    linked = subscription.stripe_subscription_id
    already_activated_by_checkout = (
        invoice.get("billing_reason") == FIRST_INVOICE and linked == provider_subscription_id
    )
    other_subscription = bool(linked) and linked != provider_subscription_id
    newer = period is not None and (
        subscription.period_end is None or period[1] > subscription.period_end
    )
    Change = type(subscription).Change
    if invoice.get("billing_reason") == PLAN_CHANGE_INVOICE:
        # The upgrade is paid: the plan changes now and the period stays as it is.
        if not other_subscription and subscription.pending_change == Change.UPGRADE and plan:
            activate(
                subscription.company_id,
                plan,
                period_start=subscription.period_start,
                period_end=subscription.period_end,
                renewal=True,
                stripe_customer_id=subscription.stripe_customer_id,
                stripe_subscription_id=subscription.stripe_subscription_id,
            )
        elif not other_subscription:
            logger.warning("A paid plan-change invoice matches no waiting upgrade.")
    elif (
        newer and plan is not None and not already_activated_by_checkout and not other_subscription
    ):
        downgrading = (
            subscription.pending_change == Change.DOWNGRADE and plan == subscription.pending_plan
        )
        activate(
            subscription.company_id,
            plan,
            period_start=period[0],
            period_end=period[1],
            renewal=True,
            stripe_customer_id=str(
                _dig(invoice, "customer", "id") or invoice.get("customer") or ""
            ),
            stripe_subscription_id=provider_subscription_id,
        )
        CheckoutAttempt.objects.filter(
            company_id=subscription.company_id, plan=plan, status=CheckoutAttempt.Status.OPEN
        ).update(status=CheckoutAttempt.Status.ACTIVATED)
        if downgrading:
            warn_over_limits(subscription.company_id)
    if not other_subscription and (
        subscription.provider_paid_at is None or paid_at > subscription.provider_paid_at
    ):
        type(subscription).objects.filter(pk=subscription.pk).update(provider_paid_at=paid_at)


def handle_payment_failed(event):
    invoice = event["data"]["object"]
    provider_subscription_id, metadata = _subscription_id(invoice), _metadata(invoice)
    company_id = _company_for(provider_subscription_id, metadata)
    if company_id is None:
        return _unmatched(event)
    failed_at = _at(event["created"])
    with transaction.atomic():
        _lock(company_id)
        subscription = get_subscription(company_id)
        _, created = record_event(
            provider_event_id=event["id"],
            company_id=company_id,
            kind="failure",
            amount_minor=invoice.get("amount_due") or 0,
            currency=invoice["currency"],
            occurred_at=failed_at,
            reason=FAILURE_REASON.format(attempt=invoice.get("attempt_count") or 1),
            plan_id=subscription.plan_id,
        )
        if not created:
            return DUPLICATE
        later_payment_seen = (
            subscription.provider_paid_at is not None and failed_at <= subscription.provider_paid_at
        )
        ours = subscription.stripe_subscription_id == provider_subscription_id
        if ours and not later_payment_seen and effective_state(subscription) == State.ACTIVE:
            mark_past_due(company_id)
    return HANDLED


def handle_subscription_deleted(event):
    provider_subscription = event["data"]["object"]
    provider_subscription_id = str(provider_subscription.get("id") or "")
    company_id = _company_for(provider_subscription_id, provider_subscription.get("metadata") or {})
    if company_id is None:
        return _unmatched(event)
    with transaction.atomic():
        _lock(company_id)
        subscription = get_subscription(company_id)
        # An old subscription's end never touches a newer one, and a repeat finds it cancelled.
        if (
            subscription.stripe_subscription_id == provider_subscription_id
            and subscription.state == State.ACTIVE
        ):
            cancel(company_id)
    return HANDLED


def handle_card_added(event):
    """A card was added to a customer: remembered by time only, so an owner coming back from the
    card page is told the truth even when the provider cannot be read at that moment."""
    from .models import Subscription

    customer_id = str(event["data"]["object"].get("customer") or "")
    if not customer_id:
        return UNMATCHED
    added_at = _at(event["created"])
    matched = Subscription.objects.filter(stripe_customer_id=customer_id).filter(
        Q(card_changed_at__isnull=True) | Q(card_changed_at__lt=added_at)
    )
    matched.update(card_changed_at=added_at)
    return HANDLED


HANDLERS = {
    "payment_method.attached": handle_card_added,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_payment_failed,
    "customer.subscription.deleted": handle_subscription_deleted,
}


def handle_event(event):
    handler = HANDLERS.get(event["type"])
    return handler(event) if handler else IGNORED
