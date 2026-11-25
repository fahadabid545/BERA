"""The one file that talks to the payment provider (Stripe). Card details are typed on the
provider's own page and never reach this server: all we send is the plan, its price and where to
come back to, and all we read is the status of the provider's checkout session.

Test mode only for now: a key that is not a test key is refused, so real money cannot move
before the business is registered."""

import logging
from dataclasses import dataclass
from uuid import uuid4

import stripe
from django.conf import settings

from core.errors import AppError

logger = logging.getLogger(__name__)

TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")
LIVE_KEY_PREFIXES = ("sk_live_", "rk_live_")
UNAVAILABLE_CODE = "payments_unavailable"
PROVIDER_CODE = "payment_provider_error"
PROVIDER_MESSAGE = "We could not reach the payment page. Please try again in a moment."
NETWORK_RETRIES = 2  # safe: every create call carries an idempotency key


def _key():
    key = settings.STRIPE_SECRET_KEY
    live_ok = settings.STRIPE_ALLOW_LIVE_KEYS and key.startswith(LIVE_KEY_PREFIXES)
    if not (key.startswith(TEST_KEY_PREFIXES) or live_ok):
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
    customer_id,
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
            customer=customer_id,
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


APPLIED, NEEDS_ACTION, DECLINED = "applied", "needs_action", "declined"


@dataclass(frozen=True)
class PriceChange:
    status: str  # applied, needs_action (the bank wants a check) or declined
    url: str = ""  # where the person completes the bank check


def _void_open_invoice(subscription_id):
    """A declined upgrade leaves an unpaid invoice that could still be paid later and change the
    price behind our back, so it is voided. A failure here is logged, never hidden."""
    try:
        invoice = stripe.Subscription.retrieve(subscription_id, api_key=_key())["latest_invoice"]
        invoice_id = invoice if isinstance(invoice, str) else invoice["id"]
        if stripe.Invoice.retrieve(invoice_id, api_key=_key())["status"] == "open":
            stripe.Invoice.void_invoice(invoice_id, api_key=_key())
    except stripe.StripeError:
        logger.warning("An unpaid plan-change invoice could not be voided.", exc_info=True)


def _outcome_of(updated):
    """An upgrade is applied only when its payment went through. Otherwise the provider keeps
    the old price and holds the change as pending."""
    if not updated.get("pending_update"):
        return PriceChange(APPLIED)
    invoice = updated["latest_invoice"]
    payment = invoice.get("payment_intent") or {}
    if payment.get("status") == "requires_action":
        return PriceChange(NEEDS_ACTION, url=invoice.get("hosted_invoice_url") or "")
    return PriceChange(DECLINED)


def change_subscription_price(
    *, subscription_id, company_id, plan, currency, amount_minor, immediate, idempotency_key
):
    """Moves the monthly subscription to the plan's price. `immediate` (an upgrade) charges the
    difference for the rest of the period now and keeps the update pending until that payment
    succeeds, so a failed card leaves the old price. Otherwise (a downgrade, or taking one back)
    nothing is charged or credited and the new price starts with the next invoice."""
    try:
        item = stripe.Subscription.retrieve(
            subscription_id, api_key=_key(), max_network_retries=NETWORK_RETRIES
        )["items"]["data"][0]
        price = stripe.Price.create(
            api_key=_key(),
            idempotency_key=f"{idempotency_key}-price",
            max_network_retries=NETWORK_RETRIES,
            currency=currency.lower(),
            unit_amount=amount_minor,
            recurring={"interval": "month"},
            product_data={"name": plan.name},
        )
        options = {
            "items": [{"id": item["id"], "price": price["id"]}],
            "metadata": {"company_id": str(company_id), "plan_id": str(plan.pk)},
            "proration_behavior": "always_invoice" if immediate else "none",
        }
        if immediate:
            options["payment_behavior"] = "pending_if_incomplete"
            options["expand"] = ["latest_invoice.payment_intent"]
        updated = stripe.Subscription.modify(
            subscription_id,
            api_key=_key(),
            idempotency_key=idempotency_key,
            max_network_retries=NETWORK_RETRIES,
            **options,
        )
    except stripe.CardError:
        _void_open_invoice(subscription_id)
        return PriceChange(DECLINED)
    except stripe.StripeError as error:
        raise _provider_error() from error
    outcome = _outcome_of(updated) if immediate else PriceChange(APPLIED)
    if outcome.status == DECLINED:
        _void_open_invoice(subscription_id)
    return outcome


def set_renewal_stops_at_period_end(subscription_id, stops):
    """Cancels (or takes back the cancellation of) the renewal: the provider keeps charging
    nothing more but the paid period runs on. Returns False when the subscription already ended
    at the provider, which cannot be taken back."""
    try:
        current = stripe.Subscription.retrieve(
            subscription_id, api_key=_key(), max_network_retries=NETWORK_RETRIES
        )
        if current["status"] == "canceled":
            return False
        stripe.Subscription.modify(
            subscription_id,
            api_key=_key(),
            idempotency_key=f"renewal-{subscription_id}-{'stop' if stops else 'resume'}-{uuid4()}",
            max_network_retries=NETWORK_RETRIES,
            cancel_at_period_end=stops,
        )
    except stripe.StripeError as error:
        raise _provider_error() from error
    return True


def end_subscription(subscription_id):
    """Ends the subscription at the provider now, so a company whose access ended is never
    charged again. Never blocks the caller: a refusal or an outage is logged and reported."""
    try:
        current = stripe.Subscription.retrieve(subscription_id, api_key=_key())
        if current["status"] != "canceled":
            stripe.Subscription.cancel(subscription_id, api_key=_key())
    except (stripe.StripeError, AppError):
        logger.warning("A provider subscription could not be ended.", exc_info=True)
        return False
    return True


CARD_UPDATE_FLOW = {"type": "payment_method_update"}  # opens the portal on the card screen


def create_portal_session(*, customer_id, return_url, flow=None):
    """The address of the provider's own billing page (card update and invoices). What it
    allows is set in the provider's portal settings, never here. A `flow` opens it straight on
    one screen."""
    extra = {"flow_data": flow} if flow else {}
    try:
        session = stripe.billing_portal.Session.create(
            api_key=_key(),
            max_network_retries=NETWORK_RETRIES,
            customer=customer_id,
            return_url=return_url,
            **extra,
        )
    except stripe.StripeError as error:
        raise _provider_error() from error
    return session["url"]


def default_card(customer_id, subscription_id=""):
    """The card the provider charges by default: its id and what is printed on a card receipt
    (brand, last four digits, expiry), or None. Read from the provider every time and never
    stored here. The subscription's own card wins over the customer's."""
    try:
        method = None
        if subscription_id:
            method = stripe.Subscription.retrieve(
                subscription_id, expand=["default_payment_method"], api_key=_key()
            )["default_payment_method"]
        if not method:
            customer = stripe.Customer.retrieve(
                customer_id, expand=["invoice_settings.default_payment_method"], api_key=_key()
            )
            method = customer["invoice_settings"]["default_payment_method"]
    except stripe.StripeError as error:
        raise _provider_error() from error
    card = method.get("card") if method else None
    if not card:
        return None
    return {
        "payment_method_id": method["id"],
        "brand": card["brand"],
        "last4": card["last4"],
        "exp_month": card["exp_month"],
        "exp_year": card["exp_year"],
    }


def retry_open_invoice(subscription_id):
    """Asks the provider to charge the subscription's open invoice again, now that the card
    changed. Never blocks the caller (the card is already updated): a declined card or an outage
    is logged and reported as False. The paid notice, not this call, restores access."""
    try:
        invoice = stripe.Subscription.retrieve(
            subscription_id, expand=["latest_invoice"], api_key=_key()
        )["latest_invoice"]
        if not invoice or invoice["status"] != "open":
            return False
        stripe.Invoice.pay(invoice["id"], api_key=_key())
    except (stripe.StripeError, AppError):
        logger.warning("An open invoice could not be paid again.", exc_info=True)
        return False
    return True


TAX_NUMBER_FIELD = "Tax number"  # the label on invoices; Stripe copies it onto each invoice


def _customer_fields(*, company_id, name, address, tax_number):
    """What the provider needs to print on invoices; nothing else about the company is sent."""
    return {
        "name": name,
        "address": address,
        "metadata": {"company_id": str(company_id)},
        "invoice_settings": {
            "custom_fields": [{"name": TAX_NUMBER_FIELD, "value": tax_number}] if tax_number else ""
        },
    }


def create_customer(*, idempotency_key, company_id, name, address, tax_number):
    try:
        customer = stripe.Customer.create(
            api_key=_key(),
            idempotency_key=idempotency_key,
            max_network_retries=NETWORK_RETRIES,
            **_customer_fields(
                company_id=company_id, name=name, address=address, tax_number=tax_number
            ),
        )
    except stripe.StripeError as error:
        raise _provider_error() from error
    return customer["id"]


def update_customer(customer_id, *, company_id, name, address, tax_number):
    """New details apply to invoices made from now on; the provider never changes one it has
    already finalised."""
    try:
        stripe.Customer.modify(
            customer_id,
            api_key=_key(),
            idempotency_key=f"customer-update-{customer_id}-{uuid4()}",
            max_network_retries=NETWORK_RETRIES,
            **_customer_fields(
                company_id=company_id, name=name, address=address, tax_number=tax_number
            ),
        )
    except stripe.StripeError as error:
        raise _provider_error() from error
