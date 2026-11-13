"""An admin sets or clears a limit for one company. The override wins over the plan's value
(`plans.limits.limit_for`) and applies at once. A value below what the company already uses
blocks new work only; nothing that exists is ever deleted."""

from django.db import transaction

from audit.service import record
from companies.models import Company
from core.errors import AppError
from emailing.links import build_link
from emailing.service import send_email

from .limits import LIMIT_NAMES, limit_for
from .models import LimitOverride
from .subscriptions import owner_of

TITLE = "Your plan limits were changed"


def _tell_the_owner(company_id, name, new_value):
    owner = owner_of(company_id)
    if owner is None:
        return
    shown = name.replace("_", " ")
    send_email(
        "usage_notice",
        owner.email,
        name=owner.name,
        title=TITLE,
        message=f"Support changed your company's limit for {shown} to {new_value:,}.",
        link=build_link("/company/billing"),
    )


def _checked(name):
    if name not in LIMIT_NAMES:
        raise AppError("unknown_limit", "This limit does not exist.", status_code=404)


def set_limit(company_id, name, value, *, by, reason):
    """Sets the company's own value for a limit (any valid value, higher or lower)."""
    _checked(name)
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=company_id)
        before = LimitOverride.objects.filter(company=company, name=name).first()
        if before and before.value == value:
            raise AppError("nothing_changed", "Nothing was changed.", status_code=400)
        old = before.value if before else limit_for(company_id, name)
        LimitOverride.objects.update_or_create(
            company=company, name=name, defaults={"value": value}
        )
        record(
            "admin.limit_changed",
            actor=by,
            target=company,
            reason=reason,
            details={"limit": name},
            changes={"value": {"old": old, "new": value}},
        )
        _tell_the_owner(company_id, name, value)


def clear_limit(company_id, name, *, by, reason):
    """Returns the company to its plan's value for a limit."""
    _checked(name)
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=company_id)
        override = LimitOverride.objects.filter(company=company, name=name).first()
        if override is None:
            raise AppError(
                "no_override", "This company has no own value for this limit.", status_code=409
            )
        old = override.value
        override.delete()
        new = limit_for(company_id, name)
        record(
            "admin.limit_changed",
            actor=by,
            target=company,
            reason=reason,
            details={"limit": name, "cleared": True},
            changes={"value": {"old": old, "new": new}},
        )
        _tell_the_owner(company_id, name, new)
