"""Revenue as money actually received: the payment records written from the provider's own
notices (`plans.payments.record_event`), never a price list. Payments minus refunds, in US dollars
(the only currency the platform charges). Every figure is for a stretch of days, `start` up to but
not including `end`, so the overview, the margin and the history agree."""

from datetime import UTC, datetime, time
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth

from .models import PaymentEvent
from .pricing import USD

MINOR_UNITS = Decimal(100)
Kind = PaymentEvent.Kind


def _net(prefix=""):
    return Sum(
        "amount_minor",
        filter=Q(**{f"{prefix}kind": Kind.PAYMENT}),
    ) - Sum("amount_minor", filter=Q(**{f"{prefix}kind": Kind.REFUND}))


def _during(start, end):
    return PaymentEvent.objects.filter(
        currency=USD,
        occurred_at__gte=datetime.combine(start, time.min, tzinfo=UTC),
        occurred_at__lt=datetime.combine(end, time.min, tzinfo=UTC),
    )


def _dollars(minor):
    return Decimal(minor or 0) / MINOR_UNITS


def _sum_by(events, field):
    rows = events.values_list(field).annotate(
        payments=Sum("amount_minor", filter=Q(kind=Kind.PAYMENT)),
        refunds=Sum("amount_minor", filter=Q(kind=Kind.REFUND)),
    )
    return {key: _dollars((payments or 0) - (refunds or 0)) for key, payments, refunds in rows}


def received_by_company(start, end):
    """{company id: dollars received} for the days."""
    return _sum_by(_during(start, end), "company_id")


def received_by_plan(start, end):
    """{plan id: dollars received}; money with no plan on its record is under None."""
    return _sum_by(_during(start, end), "plan_id")


def received_total(start, end):
    return sum(received_by_company(start, end).values(), Decimal(0))


def received_by_month(start, end):
    """{(year, month): dollars received}."""
    events = _during(start, end).annotate(month=TruncMonth("occurred_at"))
    found = _sum_by(events, "month")
    return {(month.year, month.month): amount for month, amount in found.items()}
