"""Which price a country sees. The one place that decides it: the public plans list uses the
visitor's detected country, and everything for a signed-in company (billing, upgrade and renewal
pop-ups, plan display) must use the company's locked country through `price_for`."""

from dataclasses import dataclass
from decimal import Decimal

PAKISTAN = "PK"
USD = "USD"
PKR = "PKR"
PKR_MISSING_NOTE = "Shown in US dollars because no price in Pakistani rupees is set."


@dataclass(frozen=True)
class Price:
    currency: str
    amount: Decimal
    note: str | None = None


def price_for(plan, country):
    """Pakistan sees the PKR price when one is set, otherwise (with a note) the USD price.
    Everyone else, and an unknown or empty country, sees USD."""
    if str(country or "").strip().upper() != PAKISTAN:
        return Price(USD, plan.price_usd)
    if plan.price_pkr is None:
        return Price(USD, plan.price_usd, PKR_MISSING_NOTE)
    return Price(PKR, plan.price_pkr)
