"""Sending an email at most once per occasion, to the people who want it."""

from django.db import transaction

from core.errors import AppError
from emailing.service import send_email

from .kinds import BY_NAME, KINDS
from .models import NotificationChoice, NotificationSent


def wants(user, kind_name):
    """A required kind is always wanted; an optional one unless the person switched it off."""
    if BY_NAME[kind_name].required:
        return True
    choice = NotificationChoice.objects.filter(user=user, kind=kind_name).first()
    return choice is None or choice.enabled


def mark_handled(company_id, kind_name, key):
    """Records an occasion as dealt with, without sending anything (a lower usage level that a
    higher one makes pointless)."""
    NotificationSent.objects.get_or_create(company_id=company_id, kind=kind_name, key=key)


def notify(company_id, kind_name, key, recipients, template, **values):
    """Sends `template` to each recipient who wants it, once for this occasion. The record and
    the emails stand or fall together: a failed send leaves no record, so the next run tries
    again. Returns how many emails were sent."""
    with transaction.atomic():
        _, first_time = NotificationSent.objects.get_or_create(
            company_id=company_id, kind=kind_name, key=key
        )
        if not first_time:
            return 0
        sent = 0
        for person in recipients:
            if wants(person, kind_name):
                send_email(template, person.email, name=person.name, **values)
                sent += 1
        return sent


def choices_of(user):
    return [
        {
            "kind": kind.name,
            "label": kind.label,
            "required": kind.required,
            "enabled": wants(user, kind.name),
        }
        for kind in KINDS
    ]


def set_choice(user, kind_name, enabled):
    kind = BY_NAME.get(kind_name)
    if kind is None:
        raise AppError("unknown_notification", "This notification does not exist.", status_code=404)
    if kind.required:
        raise AppError(
            "notification_required",
            "This email cannot be switched off.",
            status_code=409,
        )
    NotificationChoice.objects.update_or_create(
        company_id=user.company_id, user=user, kind=kind_name, defaults={"enabled": enabled}
    )
    return choices_of(user)
