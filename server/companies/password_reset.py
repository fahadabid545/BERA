"""Forgetting a password and choosing a new one through a link in an email."""

from django.db import transaction
from django.utils import timezone

from core.errors import AppError
from emailing.link_tokens import (
    consume_link_token,
    issue_link_token,
    link_refusal,
    retire_link_tokens,
)
from emailing.links import build_link
from emailing.models import LinkToken
from emailing.rendering import duration_text, format_moment
from emailing.service import send_email
from platform_settings.service import get_setting

from .models import CompanyUser

PURPOSE = LinkToken.Purpose.RESET_PASSWORD
FORGOT_MESSAGE = "If an account exists, we sent a reset link"
SAME_PASSWORD = "Your new password must be different from your old one."


def send_reset_link(email):
    """Sends a link to an active account with this email. The caller answers the same way
    whether or not there is one, so nobody can learn which emails have accounts. Blocked and
    removed people get nothing: a new password would not let them in."""
    person = CompanyUser.objects.filter(email=email, status=CompanyUser.Status.ACTIVE).first()
    if person is None:
        return
    hours = get_setting("tokens.password_reset_hours")
    retire_link_tokens(PURPOSE, person.pk)  # only the newest link works
    token = issue_link_token(PURPOSE, person.pk, hours)
    send_email(
        "reset_password",
        person.email,
        name=person.name,
        link=build_link("/reset-password", token=token),
        expires_in=duration_text(hours, "hour"),
    )


@transaction.atomic
def reset_password(token, new_password):
    """Spends the link and sets the new password. If the password is refused the link is not
    spent (the error undoes it), so the person can choose another within the hour.

    Saving the new password ends every session of the person (see signin/signals.py); nobody
    is signed in by a reset, so the person has to log in again."""
    person_id = consume_link_token(token, PURPOSE)
    person = (
        CompanyUser.objects.select_for_update()
        .filter(pk=person_id)
        .exclude(status__in=[CompanyUser.Status.REMOVED, CompanyUser.Status.BLOCKED])
        .first()
    )
    if person is None:
        raise link_refusal("link_invalid", "This link is not valid.")
    if person.check_password(new_password):
        raise AppError(
            "validation_error",
            "Please check the form and try again.",
            status_code=400,
            fields={"password": SAME_PASSWORD},
        )
    person.set_password(new_password)
    person.save()
    retire_link_tokens(PURPOSE, person.pk)
    send_email(
        "password_changed",
        person.email,
        name=person.name,
        when=format_moment(timezone.now()),
        link=build_link("/forgot-password"),
    )
