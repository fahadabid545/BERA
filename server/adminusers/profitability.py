"""Cost versus revenue: whether each company, and the platform as a whole, is profitable.

Per company: the AI cost of the last `admin_dashboard.margin_days` days (the same window as the
overview's margin, summed from the AI call records, which were priced when each call was made),
the amount paid, and the margin. Companies under `profitability.warning_margin_percent` are
flagged.

"Amount paid" is the money actually received in those days: the company's payment records
(payments minus refunds, `plans.revenue`). Everyone is charged in US dollars, so no conversion is
needed; the PKR rate a super admin may set is kept for when rupee charging exists. Money and AI
figures are for super admins only (`payment.view`).
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
from plans import revenue
from plans.models import Subscription
from plans.pricing import USD
from plans.subscriptions import State, effective_state
from platform_settings.models import PlatformSetting
from platform_settings.service import get_setting

PERCENT = 100
RATE_KEY = "billing.pkr_per_usd"


def _rate():
    value = get_setting(RATE_KEY)
    return None if value is None else Decimal(str(value))


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


def _row(company, subscription, cost, paid):
    state = effective_state(subscription) if subscription else State.NO_PLAN
    margin = _margin(paid, cost)
    return (
        {
            "id": str(company.pk),
            "name": company.name,
            "country": company.country,
            "subscription_state": state,
            "currency": USD,
            "amount": f"{paid:.2f}",
            "paid_usd": f"{paid:.2f}",
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
    paid = sum((paid for _, paid, _ in measured), Decimal(0))
    cost = sum((cost for _, _, cost in measured), Decimal(0))
    margin = _margin(paid, cost)
    return {
        "paid_usd": f"{paid:.2f}",
        "ai_cost": f"{cost:.6f}",
        "margin_percent": margin,
        "flagged": margin is not None
        and margin < get_setting("profitability.warning_margin_percent"),
        "companies_counted": len(measured),
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
    start, end = _window()
    received = revenue.received_by_company(start, end)
    subscriptions = {s.company_id: s for s in Subscription.objects.select_related("plan")}
    measured = [
        _row(
            company,
            subscriptions.get(company.pk),
            costs.get(company.pk) or Decimal(0),
            received.get(company.pk, Decimal(0)),
        )
        for company in Company.objects.order_by("name", "id")
    ]
    measured.sort(key=lambda item: _by_worst_margin(item[0]))
    size = get_setting("admin_companies.page_size")
    first = (page - 1) * size
    return {
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
