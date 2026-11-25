"""Stopping and restarting the monthly renewal, and opening the provider's billing page.

Cancelling keeps full access until the paid period ends; nothing is refunded or deleted. Taking
the cancellation back before then renews as before. Both change the provider first and our
record after, so a provider failure leaves both as they were. Access never comes back because a
person returned from the billing page: only the provider's paid notice (BERA-165) does that."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.security import record_security_event
from companies.models import Company
from core.errors import AppError

from . import stripe_client
from .subscriptions import State, cancel, effective_state, get_subscription, resume

PORTAL_RETURN_PATH = "/company/billing?portal=returned"


def _refuse(code, message):
    return AppError(code, message, status_code=409)


def _lock(company_id):
    Company.objects.select_for_update().get(pk=company_id)  # one billing change at a time


def cancel_renewal(company_id, *, by=None):
    with transaction.atomic():
        _lock(company_id)
        subscription = get_subscription(company_id)
        if (
            subscription.state != State.ACTIVE
            or effective_state(subscription) != State.ACTIVE
            or not subscription.renewal
            or not subscription.stripe_subscription_id
        ):
            raise _refuse(
                "cancel_unavailable", "Only a running, renewing subscription can be cancelled."
            )
        stripe_client.set_renewal_stops_at_period_end(subscription.stripe_subscription_id, True)
        return cancel(company_id, by=by)


def resume_renewal(company_id, *, by=None):
    with transaction.atomic():
        _lock(company_id)
        subscription = get_subscription(company_id)
        if (
            subscription.state != State.CANCELLED
            or effective_state(subscription) != State.CANCELLED
            or not subscription.stripe_subscription_id
        ):
            raise _refuse("resume_unavailable", "Only a cancelled subscription can be resumed.")
        if not stripe_client.set_renewal_stops_at_period_end(
            subscription.stripe_subscription_id, False
        ):
            raise _refuse(
                "resume_unavailable",
                "This subscription has already ended with the payment provider. "
                "You can buy a plan again when your access ends.",
            )
        return resume(company_id, by=by)


def open_billing_portal(company_id, *, by):
    """The provider's own page, for the company's own customer record only (our stored id, never
    anything from the request). Allowed in every state that has a customer, Past due and
    view-only included, so a failed card can always be fixed."""
    subscription = get_subscription(company_id)
    if not subscription.stripe_customer_id:
        raise _refuse(
            "no_billing_account", "There is no card billing for your company yet. Buy a plan first."
        )
    url = stripe_client.create_portal_session(
        customer_id=subscription.stripe_customer_id,
        return_url=f"{settings.WEB_BASE_URL}{PORTAL_RETURN_PATH}",
    )
    record_security_event(
        "security.billing_portal_opened",
        actor=by,
        target=Company.objects.get(pk=company_id),
        details={"state": effective_state(subscription, timezone.now())},
    )
    return url
