"""Buying a plan by card. The company is sent to the payment provider's own page (card details
never reach this server); the subscription is activated only after the server has asked the
provider whether that page was paid, never because the browser says it came back. Starting is
safe to repeat and activating happens once. Renewals, cancellation, webhooks and the grace
period belong to later tickets."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from companies.models import Company
from core.errors import AppError, not_found
from platform_settings.branding import contact_support
from platform_settings.service import get_setting
from usage.service import add_months

from . import stripe_client
from .models import CheckoutAttempt, Plan
from .pricing import charge_price
from .subscriptions import State, activate, effective_state, get_subscription

Status = CheckoutAttempt.Status
CAN_BUY = frozenset({State.NO_PLAN, State.EXPIRED})
PAID, PENDING, CANCELLED, CLOSED = "activated", "pending", "cancelled", "closed"
MINOR_UNITS = Decimal(100)


def _refuse(code, message):
    return AppError(code, message, status_code=409)


def _lock(company_id):
    Company.objects.select_for_update().get(
        pk=company_id
    )  # one checkout step at a time per company


def _buyable_plan(plan_id):
    plan = Plan.objects.filter(pk=plan_id, status=Plan.Status.ACTIVE).first()
    if plan is None or plan.price_usd is None:
        raise not_found()
    return plan


def _live_attempts(company_id, now):
    window = timedelta(minutes=get_setting("billing.checkout_minutes"))
    return CheckoutAttempt.objects.filter(
        company_id=company_id, status=Status.OPEN, created_at__gt=now - window
    )


def _close_other_pages(attempts):
    """A company pays on one page at a time: a page for another plan is closed first, so two
    cannot both be paid. If the provider will not close one, it may be paying right now."""
    for attempt in attempts:
        if not stripe_client.expire_checkout_session(attempt.stripe_session_id):
            raise _refuse(
                "checkout_in_progress",
                "Another payment is still open. Finish it or wait a few minutes, then try again.",
            )
        attempt.status = Status.REPLACED
        attempt.save(update_fields=["status"])


def start_checkout(company_id, plan_id):
    """The address of the provider's payment page for this plan. A second call for the same
    plan while a page is open (a double click) returns the same page and creates nothing."""
    plan = _buyable_plan(plan_id)
    now = timezone.now()
    with transaction.atomic():
        _lock(company_id)
        if effective_state(get_subscription(company_id), now) not in CAN_BUY:
            raise _refuse(
                "already_subscribed", "Your company already has a plan. It cannot be bought again."
            )
        live = list(_live_attempts(company_id, now))
        same = next((a for a in live if a.plan_id == plan.pk and a.payment_page_url), None)
        if same is not None:
            return same.payment_page_url
        _close_other_pages(live)
        price = charge_price(plan)
        attempt = CheckoutAttempt.objects.create(
            company_id=company_id,
            plan=plan,
            amount_minor=int(price.amount * MINOR_UNITS),
            currency=price.currency,
        )
        session = stripe_client.create_checkout_session(
            idempotency_key=str(
                attempt.pk
            ),  # a retry of this very attempt never makes a second page
            company_id=company_id,
            plan=plan,
            currency=price.currency,
            amount_minor=attempt.amount_minor,
            expires_at=now + timedelta(minutes=get_setting("billing.checkout_minutes")),
            success_url=f"{settings.WEB_BASE_URL}/company/billing/return?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.WEB_BASE_URL}/company/billing?checkout=cancelled",
        )
        attempt.stripe_session_id = session.id
        attempt.payment_page_url = session.url
        attempt.save(update_fields=["stripe_session_id", "payment_page_url"])
        return attempt.payment_page_url


def _id_of(reference):
    """The provider returns an id or the object itself, depending on what was expanded."""
    return getattr(reference, "id", reference) or ""


def confirm_checkout(company_id, session_id):
    """Asks the provider what happened to the page and activates the plan if, and only if, it
    was paid. Returns one of: activated (also when it was activated before: opening the return
    page twice changes nothing), pending, cancelled, closed."""
    attempt = CheckoutAttempt.objects.filter(
        company_id=company_id, stripe_session_id=str(session_id)
    ).first()
    if attempt is None:
        raise not_found()
    session = stripe_client.retrieve_checkout_session(attempt.stripe_session_id)
    with transaction.atomic():
        _lock(company_id)
        attempt = CheckoutAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status == Status.ACTIVATED:
            return PAID
        if attempt.status == Status.REPLACED:
            return CLOSED
        if session.status == "expired":
            return CANCELLED
        if not (session.status == "complete" and session.payment_status == "paid"):
            return PENDING
        _check_matches_what_was_asked(attempt, session, company_id)
        now = timezone.now()
        activate(
            company_id,
            attempt.plan,
            period_start=now,
            period_end=add_months(now, 1),
            renewal=True,
            stripe_customer_id=_id_of(session.customer),
            stripe_subscription_id=_id_of(session.subscription),
        )
        attempt.status = Status.ACTIVATED
        attempt.save(update_fields=["status"])
        return PAID


def _check_matches_what_was_asked(attempt, session, company_id):
    """A paid session that is not the one we made (other company, amount or currency) is never
    trusted."""
    same = (
        session.client_reference_id == str(company_id)
        and session.amount_total == attempt.amount_minor
        and str(session.currency).upper() == attempt.currency
    )
    if not same:
        raise AppError(
            "payment_mismatch",
            "This payment does not match your order. " + contact_support(),
            status_code=409,
        )
