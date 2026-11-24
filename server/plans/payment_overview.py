"""The admin's view of payment records: a filtered, paged list and totals per currency.

Amounts of different currencies are never added together. Totals follow the filters, so they
always describe the rows being looked at.
"""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum

from companies.models import Company
from core.errors import form_error
from platform_settings.service import get_setting

from .models import PaymentEvent

# Both currencies the platform charges in (USD and PKR) have two decimals: 100 minor units each.
MINOR_UNITS_PER_UNIT = Decimal(100)
AMOUNT_PLACES = Decimal("0.01")
KINDS = PaymentEvent.Kind


def money(amount_minor):
    return str((Decimal(amount_minor) / MINOR_UNITS_PER_UNIT).quantize(AMOUNT_PLACES))


def _start_of_day(day):
    return datetime.combine(day, time.min, tzinfo=UTC)


def _filtered(filters):
    events = PaymentEvent.objects.all()
    if filters.get("kind"):
        events = events.filter(kind=filters["kind"])
    if filters.get("company"):
        events = events.filter(company_id=filters["company"])
    if filters.get("currency"):
        events = events.filter(currency=filters["currency"])
    if filters.get("from_date"):
        events = events.filter(occurred_at__gte=_start_of_day(filters["from_date"]))
    if filters.get("to_date"):  # the whole of the last day counts
        events = events.filter(
            occurred_at__lt=_start_of_day(filters["to_date"] + timedelta(days=1))
        )
    return events


def _totals(events):
    rows = events.values("currency", "kind").annotate(count=Count("pk"), amount=Sum("amount_minor"))
    by_currency = {}
    for row in rows:
        entry = by_currency.setdefault(
            row["currency"],
            {
                "currency": row["currency"],
                "payments": {"count": 0, "amount": money(0)},
                "refunds": {"count": 0, "amount": money(0)},
                "failures": {"count": 0},
            },
        )
        if row["kind"] == KINDS.FAILURE:
            entry["failures"]["count"] = row["count"]
        else:
            group = "payments" if row["kind"] == KINDS.PAYMENT else "refunds"
            entry[group] = {"count": row["count"], "amount": money(row["amount"])}
    return sorted(by_currency.values(), key=lambda entry: entry["currency"])


def _item(event, names):
    return {
        "id": str(event.pk),
        "provider_event_id": event.provider_event_id,
        "kind": event.kind,
        "company_id": event.company_id,
        "company": names[event.company_id],
        "amount": money(event.amount_minor),
        "currency": event.currency,
        "reason": event.reason,
        "at": event.occurred_at.isoformat(),
    }


def overview(filters, page):
    """Payments, refunds and failures newest first for the filters (`kind`, `company`, `currency`,
    `from_date`, `to_date`), one page of `admin_payments.page_size`, with totals per currency and
    the companies and currencies that have records to filter by."""
    if (
        filters.get("from_date")
        and filters.get("to_date")
        and filters["from_date"] > filters["to_date"]
    ):
        raise form_error({"to_date": "This must not be before the start date."})
    events = _filtered(filters)
    size = get_setting("admin_payments.page_size")
    total = events.count()
    shown = list(events.order_by("-occurred_at", "-pk")[(page - 1) * size : page * size])
    names = dict(
        Company.objects.filter(pk__in={event.company_id for event in shown}).values_list(
            "pk", "name"
        )
    )
    everyone = PaymentEvent.objects.values_list("company_id", flat=True).distinct()
    return {
        "total": total,
        "page": page,
        "page_size": size,
        "totals": _totals(events),
        "items": [_item(event, names) for event in shown],
        "companies": [
            {"id": company.pk, "name": company.name}
            for company in Company.objects.filter(pk__in=everyone).order_by("name", "pk")
        ],
        "currencies": sorted(PaymentEvent.objects.values_list("currency", flat=True).distinct()),
    }
