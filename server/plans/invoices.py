"""The invoices a company has been issued. The payment provider makes them (no invoice file is
generated here); we keep a copy of each when its paid notice arrives, with the name, address and
tax number it was made out with. That snapshot never changes, whatever the company edits later.

The provider's links open a page or PDF without further sign-in, so they are handed out only by
`link_for`, behind the owner check, and are never put in logs, emails or the audit log."""

from core.errors import AppError

from .billing_details import get_details
from .models import BillingDetails, Invoice
from .stripe_client import TAX_NUMBER_FIELD

PDF, HOSTED = "pdf", "hosted"
KINDS = (PDF, HOSTED)
UNAVAILABLE_MESSAGE = "This invoice file is not ready yet. Please try again in a little while."


def _address_text(address):
    """An address as the lines a person would read, empty parts left out."""
    address = address or {}
    place = " ".join(part for part in (address.get("postal_code"), address.get("city")) if part)
    lines = [address.get("line1"), address.get("line2"), place, address.get("state")]
    return "\n".join([*(line for line in lines if line), address.get("country") or ""]).strip()


def _tax_number_of(invoice):
    for field in invoice.get("custom_fields") or []:
        if field.get("name") == TAX_NUMBER_FIELD:
            return field.get("value") or ""
    return ""


def _snapshot(company_id, invoice):
    """Who the invoice is made out to: the provider's own copy of it, else the company's details
    at the moment its paid notice is read."""
    name = invoice.get("customer_name") or ""
    address = _address_text(invoice.get("customer_address"))
    tax_number = _tax_number_of(invoice)
    if name or address:
        return name, address, tax_number
    details = get_details(company_id)
    if details is None:
        return "", "", ""
    return details.name, _address_text(_address_of(details)), details.tax_number


def _address_of(details: BillingDetails):
    return {
        "line1": details.address_line1,
        "line2": details.address_line2,
        "city": details.city,
        "state": details.state,
        "postal_code": details.postal_code,
        "country": details.country,
    }


def store_invoice(company_id, plan, invoice, *, issued_at, period):
    """Keeps the paid invoice once. A repeated notice finds it and changes nothing."""
    name, address, tax_number = _snapshot(company_id, invoice)
    start, end = period if period else (None, None)
    stored, _ = Invoice.objects.get_or_create(
        provider_invoice_id=invoice["id"],
        defaults={
            "company_id": company_id,
            "number": invoice.get("number") or "",
            "amount_minor": invoice["amount_paid"],
            "currency": invoice["currency"].upper(),
            "issued_at": issued_at,
            "period_start": start,
            "period_end": end,
            "plan": plan,
            "billed_to_name": name,
            "billed_to_address": address,
            "billed_to_tax_number": tax_number,
            "hosted_url": invoice.get("hosted_invoice_url") or "",
            "pdf_url": invoice.get("invoice_pdf") or "",
        },
    )
    return stored


def list_invoices(company_id):
    """Newest first, without the provider's links."""
    rows = Invoice.objects.filter(company_id=company_id).select_related("plan")
    return [
        {
            "id": str(row.pk),
            "number": row.number,
            "issued_at": row.issued_at,
            "amount_minor": row.amount_minor,
            "currency": row.currency,
            "plan_name": row.plan.name if row.plan else None,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "billed_to_name": row.billed_to_name,
            "billed_to_address": row.billed_to_address,
            "billed_to_tax_number": row.billed_to_tax_number,
            "can_download": bool(row.pdf_url),
            "can_view": bool(row.hosted_url),
        }
        for row in rows.order_by("-issued_at")
    ]


def link_for(invoice, kind):
    """The provider's address of one of the company's own invoices (the caller found it through
    the company's own records)."""
    url = invoice.pdf_url if kind == PDF else invoice.hosted_url
    if not url:
        raise AppError("invoice_file_unavailable", UNAVAILABLE_MESSAGE, status_code=409)
    return url
