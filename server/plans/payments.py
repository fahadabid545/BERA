"""Payment records: the one place a payment, refund or failed payment is written.

Whatever reports a payment (the provider's webhook when real payments exist, a test) calls
`record_event` with the provider's own event id. The same event arriving again changes nothing and
returns the record it already made, so records always match the provider's events one to one. The
same event id with different content is a mistake in the sender, not something to overwrite, and is
refused. Nothing here reads or stores card or personal data.
"""

from django.db import IntegrityError, transaction

from companies.models import Company
from core.errors import AppError

from .models import PaymentEvent

CONFLICT_CODE = "payment_event_conflict"
CONFLICT_MESSAGE = "This payment event was already recorded with different details."
INVALID_CODE = "payment_event_invalid"
SAME_EVENT_FIELDS = ("company_id", "kind", "amount_minor", "currency", "reason", "occurred_at")


def _checked(values):
    """The values as they are stored, or `AppError` for something that cannot be a payment."""
    problems = []
    if not str(values["provider_event_id"]).strip():
        problems.append("an event id")
    if values["kind"] not in PaymentEvent.Kind.values:
        problems.append("a known kind")
    if not isinstance(values["amount_minor"], int) or values["amount_minor"] < 0:
        problems.append("an amount of zero or more")
    currency = str(values["currency"]).strip().upper()
    if not (len(currency) == 3 and currency.isalpha() and currency.isascii()):
        problems.append("a three-letter currency")
    if not Company.objects.filter(pk=values["company_id"]).exists():
        problems.append("an existing company")
    if problems:
        raise AppError(
            INVALID_CODE, "A payment record needs " + ", ".join(problems) + ".", status_code=400
        )
    return {**values, "currency": currency, "reason": str(values["reason"]).strip()[:200]}


def record_event(
    *,
    provider_event_id,
    company_id,
    kind,
    amount_minor,
    currency,
    occurred_at,
    reason="",
    plan_id=None,
):
    """Writes the record for one provider event. Returns `(record, created)`; an event seen before
    returns its existing record with `created` False."""
    values = _checked(
        {
            "provider_event_id": provider_event_id,
            "company_id": company_id,
            "kind": kind,
            "amount_minor": amount_minor,
            "currency": currency,
            "reason": reason,
            "occurred_at": occurred_at,
            "plan_id": plan_id,
        }
    )
    event_id = str(values.pop("provider_event_id")).strip()
    try:
        with transaction.atomic():
            return PaymentEvent.objects.create(provider_event_id=event_id, **values), True
    except IntegrityError:
        existing = PaymentEvent.objects.filter(provider_event_id=event_id).first()
        if existing is None:  # the failure was something else (for example an unknown company)
            raise
    if any(getattr(existing, field) != values[field] for field in SAME_EVENT_FIELDS):
        raise AppError(CONFLICT_CODE, CONFLICT_MESSAGE, status_code=409)
    return existing, False
