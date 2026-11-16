"""A person's own profile and the company's settings.

An email change is confirmed through the NEW address, and the OLD address is told once it
happened, so a thief who changes the address cannot also take over the warning (see
`account_notices.send_email_changed_notice`)."""

import logging

from django.db import transaction

from activity.service import record, retention_days
from core import rate_limits
from core.errors import form_error
from core.field_protection import normalize_email
from emailing.link_tokens import (
    consume_link_token,
    issue_link_token,
    link_refusal,
    retire_link_tokens,
)
from emailing.links import build_link
from emailing.models import LinkToken
from emailing.rendering import duration_text
from emailing.service import send_email
from platform_settings.service import get_setting
from signin.password_change import require_current_password

from .account_notices import send_email_changed_notice
from .models import CompanyUser, PendingEmailChange

logger = logging.getLogger(__name__)

PURPOSE = LinkToken.Purpose.CHANGE_EMAIL
EMAIL_SENT_MESSAGE = "If the address can be used, we have sent a link to it."
NOTHING_TO_CHANGE = "Send at least one thing to change."


def profile(person):
    return {
        "name": person.name,
        "email": person.email,
        "role": person.role,
        "company_name": person.company.name,
        "country": person.company.country,
    }


def rename(person, name):
    person.name = name
    person.save(update_fields=["name"])
    return profile(person)


def request_email_change(person, current_password, raw_new_email):
    """Sends a confirmation link to the new address. The answer is the same whether or not the
    address is free, so it cannot be used to find out who has an account; an address that is
    taken gets the "you already have an account" notice instead of a link."""
    require_current_password(person, current_password)
    new_email = normalize_email(raw_new_email)
    if new_email == person.email:
        raise form_error({"email": "This is already your email address."})
    owner_of_it = CompanyUser.objects.filter(email=new_email).first()
    if owner_of_it is not None:
        _tell_it_is_taken(owner_of_it)
        return
    hours = get_setting("tokens.email_change_hours")
    with transaction.atomic():
        PendingEmailChange.objects.update_or_create(
            person=person, defaults={"new_email": new_email}
        )
        retire_link_tokens(PURPOSE, person.pk)  # only the newest link works
        token = issue_link_token(PURPOSE, person.pk, hours)
    send_email(
        "confirm_new_email",
        new_email,
        name=person.name,
        link=build_link("/confirm-email-change", token=token),
        expires_in=duration_text(hours, "hour"),
    )


def _tell_it_is_taken(owner):
    subject = "email:" + owner.email
    if rate_limits.hit(rate_limits.SIGN_UP_NOTICE, subject):
        return  # enough notices to this inbox for now
    send_email("already_registered", owner.email, name=owner.name, link=build_link("/login"))


@transaction.atomic
def confirm_email_change(token):
    """Makes the confirmed address the person's own and tells the old address. Whoever is
    signed in plays no part: the link alone decides."""
    person_id = consume_link_token(token, PURPOSE)
    pending = (
        PendingEmailChange.objects.select_related("person").filter(person_id=person_id).first()
    )
    if pending is None or pending.person.status == CompanyUser.Status.REMOVED:
        # Raising also undoes the use of the link.
        raise link_refusal("link_invalid", "This link is not valid.")
    person = pending.person
    if CompanyUser.objects.filter(email=pending.new_email).exclude(pk=person.pk).exists():
        raise link_refusal("email_unavailable", "This email address can no longer be used.")
    previous_address = person.email
    person.email = pending.new_email
    person.email_verified = True  # it was just proven through the new address
    person.save(update_fields=["email", "email_verified"])
    pending.delete()
    send_email_changed_notice(person, previous_address)


def company_settings(company):
    choices = get_setting("retention.choices_days")
    return {
        "name": company.name,
        "country": company.country,  # the billing country: shown, never changed here
        "retention": {
            "days": retention_days(company.pk),  # what is in force now
            "chosen": company.retention_days if company.retention_days in choices else None,
            "default_days": get_setting("retention.default_days"),
            "choices": choices,
        },
    }


def update_company(owner, company, changes):
    """The owner changes the company's name and/or how long its activity log is kept (one of the
    platform's choices, or None for the platform default)."""
    if not changes:
        raise form_error({"name": NOTHING_TO_CHANGE})
    if "retention_days" in changes:
        days = changes["retention_days"]
        if days is not None and days not in get_setting("retention.choices_days"):
            raise form_error({"retention_days": "Choose one of the offered times."})
    with transaction.atomic():
        if "name" in changes:
            company.name = changes["name"]
            _log(owner, company, {"setting": "company_name"})
        if "retention_days" in changes:
            company.retention_days = changes["retention_days"]
            _log(owner, company, {"setting": "retention", "days": changes["retention_days"] or 0})
        company.save(update_fields=["name", "retention_days"])
    return company_settings(company)


def _log(owner, company, details):
    record("setting_changed", company_id=company.pk, actor=owner, details=details)
