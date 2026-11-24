"""The one file that talks to the payment provider (Stripe). Card details are typed on the
provider's own page and never reach this server: all we send is the plan, its price and where to
come back to, and all we read is the status of the provider's checkout session.

Test mode only for now: a key that is not a test key is refused, so real money cannot move
before real payments are built (BERA-166)."""

import stripe
from django.conf import settings

from core.errors import AppError

TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")
UNAVAILABLE_CODE = "payments_unavailable"
PROVIDER_CODE = "payment_provider_error"
PROVIDER_MESSAGE = "We could not reach the payment page. Please try again in a moment."
NETWORK_RETRIES = 2  # safe: every create call carries an idempotency key


def _key():
    key = settings.STRIPE_SECRET_KEY
    if not key.startswith(TEST_KEY_PREFIXES):
        raise AppError(
            UNAVAILABLE_CODE, "Card payments are not available right now.", status_code=503
        )
    return key


def _provider_error():
    # The provider's message can name internals; the company sees one plain sentence.
    return AppError(PROVIDER_CODE, PROVIDER_MESSAGE, status_code=502)


def create_checkout_session(
    *,
    idempotency_key,
    company_id,
    plan,
    currency,
    amount_minor,
    expires_at,
    success_url,
    cancel_url,
):
    """A subscription checkout (monthly, card saved) on the provider's page. The same
    idempotency key always returns the same session, so a repeat never makes a second one."""
    try:
        return stripe.checkout.Session.create(
            api_key=_key(),
            idempotency_key=idempotency_key,
            max_network_retries=NETWORK_RETRIES,
            mode="subscription",
            client_reference_id=str(company_id),
            metadata={"company_id": str(company_id), "plan_id": str(plan.pk)},
            subscription_data={
                "metadata": {"company_id": str(company_id), "plan_id": str(plan.pk)}
            },
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": amount_minor,
                        "recurring": {"interval": "month"},
                        "product_data": {"name": plan.name},
                    },
                }
            ],
            expires_at=int(expires_at.timestamp()),
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except stripe.StripeError as error:
        raise _provider_error() from error


def retrieve_checkout_session(session_id):
    try:
        return stripe.checkout.Session.retrieve(
            session_id, api_key=_key(), max_network_retries=NETWORK_RETRIES
        )
    except stripe.StripeError as error:
        raise _provider_error() from error


def expire_checkout_session(session_id):
    """Closes a payment page nobody should pay on any more. A page already paid or closed is
    left as it is (the provider refuses; the caller checks the outcome)."""
    try:
        stripe.checkout.Session.expire(session_id, api_key=_key())
    except stripe.StripeError:
        return False
    return True
