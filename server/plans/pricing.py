"""Which price a country sees. The one place that decides it: the public plans list uses the
visitor's detected country, and everything for a signed-in company (billing, upgrade and renewal
pop-ups, plan display) must use the company's locked country through `price_for`."""

from dataclasses import dataclass
from decimal import Decimal

PAKISTAN = "PK"
USD = "USD"
PKR = "PKR"
PKR_MISSING_NOTE = "Shown in US dollars because no price in Pakistani rupees is set."
PKR_ESTIMATE_NOTE = "Estimate only. You are charged in US dollars."


@dataclass(frozen=True)
class Price:
    currency: str
    amount: Decimal
    note: str | None = None
    approximate: bool = False  # shown for information; not what the company is charged


def charge_currency():
    """The one place that says which currency customers are charged in: always US dollars, in
    every country (the payment account is in Canada). Charging Pakistani rupees later is a change
    here only, once the payment provider has confirmed that account can do it."""
    return USD


def charge_price(plan):
    """What checkout, invoices and renewals charge for a plan, whatever the buyer's country."""
    currency = charge_currency()
    return Price(currency, getattr(plan, f"price_{currency.lower()}"))


def price_for(plan, country):
    """Pakistan sees the PKR price when one is set, otherwise (with a note) the USD price.
    Everyone else, and an unknown or empty country, sees USD."""
    if str(country or "").strip().upper() != PAKISTAN:
        return Price(USD, plan.price_usd)
    if plan.price_pkr is None:
        return Price(USD, plan.price_usd, PKR_MISSING_NOTE)
    return Price(PKR, plan.price_pkr, PKR_ESTIMATE_NOTE, approximate=charge_currency() != PKR)
