"""The name, address and tax number invoices are made out to. Required (name and address)
before the first payment; the tax number is optional. Only the owner reads or changes them.

Editing updates the payment provider's customer first (when there is one), then our record, so
a provider failure leaves both as they were. It never touches invoices already issued (see
`plans.invoices`), and never the company's locked sign-up country."""

from django.db import transaction

from audit.service import record
from companies.models import Company
from core.errors import AppError

from . import stripe_client
from .models import BillingDetails

TAX_FIELD = "tax_number"
FIELDS = ("name", "address_line1", "address_line2", "city", "state", "postal_code", "country")
REQUIRED_FIELDS = ("name", "address_line1", "city", "country")
REQUIRED_MESSAGE = "Add your billing name and address before paying."


def get_details(company_id):
    return BillingDetails.objects.filter(company_id=company_id).first()


def is_complete(details):
    return details is not None and all(getattr(details, field) for field in REQUIRED_FIELDS)


def require_details(company_id):
    """The details a first payment needs, or a refusal that names what is missing."""
    details = get_details(company_id)
    if not is_complete(details):
        missing = [
            field for field in REQUIRED_FIELDS if details is None or not getattr(details, field)
        ]
        raise AppError(
            "billing_details_required",
            REQUIRED_MESSAGE,
            status_code=409,
            fields={field: "This is required." for field in missing},
        )
    return details


def _provider_address(details):
    return {
        "line1": details.address_line1,
        "line2": details.address_line2,
        "city": details.city,
        "state": details.state,
        "postal_code": details.postal_code,
        "country": details.country,
    }


def _provider_fields(details):
    return {
        "company_id": details.company_id,
        "name": details.name,
        "address": _provider_address(details),
        "tax_number": details.tax_number,
    }


def ensure_customer(details):
    """The provider's customer for these details, made once (the id is kept)."""
    if not details.stripe_customer_id:
        details.stripe_customer_id = stripe_client.create_customer(
            idempotency_key=f"customer-{details.pk}", **_provider_fields(details)
        )
        details.save(update_fields=["stripe_customer_id", "updated_at"])
    return details.stripe_customer_id


def _changes(before, new_values):
    """Old and new values of what changed. The tax number is only ever recorded as changed."""
    changes = {
        field: {"old": before.get(field, ""), "new": new_values[field]}
        for field in FIELDS
        if before.get(field, "") != new_values[field]
    }
    if before.get(TAX_FIELD, "") != new_values[TAX_FIELD]:
        changes[TAX_FIELD] = {"old": "hidden", "new": "changed"}
    return changes


def save_details(company_id, new_values, *, by):
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=company_id)
        details = get_details(company_id)
        before = {name: getattr(details, name) for name in (*FIELDS, TAX_FIELD)} if details else {}
        changes = _changes(before, new_values)
        if not changes:
            return details
        candidate = details or BillingDetails(company_id=company_id)
        for name, value in new_values.items():
            setattr(candidate, name, value)
        if candidate.stripe_customer_id:
            stripe_client.update_customer(
                candidate.stripe_customer_id, **_provider_fields(candidate)
            )
        candidate.save()
        record(
            "billing.details_changed",
            actor=by,
            target=Company.objects.get(pk=company_id),
            changes=changes,
        )
        return candidate


def shown(details):
    """What the owner sees. Empty strings for a company that has none yet."""
    values = {name: getattr(details, name, "") if details else "" for name in FIELDS}
    return {
        **values,
        TAX_FIELD: details.tax_number if details else "",
        "complete": is_complete(details),
    }
