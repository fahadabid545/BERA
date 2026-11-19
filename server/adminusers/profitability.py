"""Cost versus revenue: whether each company, and the platform as a whole, is profitable.

Per company: the AI cost of the last `admin_dashboard.margin_days` days (the same window as the
overview's margin, summed from the AI call records, which were priced when each call was made),
the amount paid, and the margin. Companies under `profitability.warning_margin_percent` are
flagged.

There are no payment records yet, so "amount paid" is an estimate: the monthly price of the
plan the company is on, in the company's own currency, while the company is paying. It all lives
in `amount_paid`, the one function real payments replace. Pakistani rupee amounts become dollars
only with the rate a super admin set; without it they are shown as "rate not set" and left out
of the totals, like a plan with no price in the company's currency. Money and AI figures are for
super admins only (`payment.view`).
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from adminusers.models import AdminUser
from ai.models import AiCall
from audit.service import record
from companies.models import Company
from core.errors import form_error
from cvs.dashboard import in_days
from plans.models import Subscription
from plans.pricing import PAKISTAN, PKR, USD
from plans.subscriptions import State, effective_state
from platform_settings.models import PlatformSetting
from platform_settings.service import get_setting

PERCENT = 100
RATE_KEY = "billing.pkr_per_usd"
PAYING = (State.ACTIVE, State.PAST_DUE, State.CANCELLED)

OK = "ok"
RATE_NOT_SET = "rate_not_set"
NO_PRICE = "no_price"


def amount_paid(subscription, state, country):
    """(currency, amount) the company pays a month, or amount None when its plan has no price in
    that currency. Free, expired and unsubscribed companies pay 0. The estimate until real
    payments exist."""
    currency = PKR if str(country or "").strip().upper() == PAKISTAN else USD
    if state not in PAYING or subscription is None or subscription.plan is None:
        return currency, Decimal(0)
    plan = subscription.plan
    return currency, plan.price_pkr if currency == PKR else plan.price_usd


def _rate():
    value = get_setting(RATE_KEY)
    return None if value is None else Decimal(str(value))


def _in_dollars(currency, amount, rate):
    """(status, dollars): what the amount is worth, or why it cannot be said."""
    if amount is None:
        return NO_PRICE, None
    if currency == USD or amount == 0:  # nothing paid needs no rate
        return OK, amount if currency == USD else Decimal(0)
    if rate is None:
        return RATE_NOT_SET, None
    return OK, amount / rate


def _margin(paid, cost):
    if not paid:
        return None
    return round(float((paid - cost) * PERCENT / paid), 1)


def _costs():
    start, end = _window()
    found = (
        in_days(AiCall.objects.all(), "created_at", start, end)
        .values_list("company_id")
        .annotate(total=Sum("estimated_cost"))
    )
    return dict(found)


def _window():
    days = get_setting("admin_dashboard.margin_days")
    today = timezone.now().date()
    return today - timedelta(days=days - 1), today + timedelta(days=1)


def _row(company, subscription, cost, rate):
    state = effective_state(subscription) if subscription else State.NO_PLAN
    currency, amount = amount_paid(subscription, state, company.country)
    status, paid = _in_dollars(currency, amount, rate)
    margin = _margin(paid, cost) if paid is not None else None
    return (
        {
            "id": str(company.pk),
            "name": company.name,
            "country": company.country,
            "subscription_state": state,
            "currency": currency,
            "amount": None if amount is None else f"{amount:.2f}",
            "status": status,
            "paid_usd": None if paid is None else f"{paid:.2f}",
            "ai_cost": f"{cost:.6f}",
            "margin_percent": margin,
            "flagged": margin is not None
            and margin < get_setting("profitability.warning_margin_percent"),
        },
        paid,
        cost,
    )


def _by_worst_margin(row):
    margin = row["margin_percent"]
    return (margin is None, margin if margin is not None else 0, row["name"].lower(), row["id"])


def _overall(measured, all_cost):
    """Totals over the companies whose amount could be turned into dollars; the others are
    counted so the gap is visible."""
    counted = [(paid, cost) for _, paid, cost in measured if paid is not None]
    paid = sum((paid for paid, _ in counted), Decimal(0))
    cost = sum((cost for _, cost in counted), Decimal(0))
    margin = _margin(paid, cost)
    return {
        "paid_usd": f"{paid:.2f}",
        "ai_cost": f"{cost:.6f}",
        "margin_percent": margin,
        "flagged": margin is not None
        and margin < get_setting("profitability.warning_margin_percent"),
        "companies_counted": len(counted),
        "left_out": {
            "rate_not_set": sum(1 for row, _, _ in measured if row["status"] == RATE_NOT_SET),
            "no_price": sum(1 for row, _, _ in measured if row["status"] == NO_PRICE),
        },
        "all_ai_cost": f"{all_cost:.6f}",
    }


def _checked_page(params):
    try:
        return max(int(params.get("page") or 1), 1)
    except ValueError as error:
        raise form_error({"page": "The page must be a number."}) from error


def cost_versus_revenue(params):
    page = _checked_page(params)
    rate, costs = _rate(), _costs()
    subscriptions = {s.company_id: s for s in Subscription.objects.select_related("plan")}
    measured = [
        _row(company, subscriptions.get(company.pk), costs.get(company.pk) or Decimal(0), rate)
        for company in Company.objects.order_by("name", "id")
    ]
    measured.sort(key=lambda item: _by_worst_margin(item[0]))
    size = get_setting("admin_companies.page_size")
    first = (page - 1) * size
    start, end = _window()
    return {
        "estimated": True,
        "days": get_setting("admin_dashboard.margin_days"),
        "warning_margin_percent": get_setting("profitability.warning_margin_percent"),
        "pkr_per_usd": None if rate is None else str(rate),
        "overall": _overall(measured, sum(costs.values(), Decimal(0))),
        "results": [row for row, _, _ in measured[first : first + size]],
        "page": page,
        "page_size": size,
        "total": len(measured),
        "pages": max(1, -(-len(measured) // size)),
        "from": start.isoformat(),
        "to": (end - timedelta(days=1)).isoformat(),
    }


def set_rate(rate, *, by: AdminUser, reason):
    """Sets (or, with None, clears) the PKR per one US dollar rate, and records who and why."""
    with transaction.atomic():
        old = get_setting(RATE_KEY)
        if rate is None:
            PlatformSetting.objects.filter(key=RATE_KEY).delete()
        else:
            PlatformSetting.objects.update_or_create(key=RATE_KEY, defaults={"value": float(rate)})
        record(
            "admin.pkr_rate_changed",
            actor=by,
            reason=reason,
            changes={
                "pkr_per_usd": {
                    "old": None if old is None else str(old),
                    "new": None if rate is None else str(rate),
                }
            },
        )
    return None if rate is None else str(rate)
