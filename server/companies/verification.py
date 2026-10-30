"""Confirming that the owner controls the email address they signed up with."""

from django.db import transaction

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

from .models import CompanyUser

PURPOSE = LinkToken.Purpose.VERIFY_EMAIL
RESEND_MESSAGE = "If this email still needs verifying, we have sent a new link."


def send_verification_email(person):
    """Sends the link, and cancels any earlier one: only the newest link works."""
    hours = get_setting("tokens.email_verification_hours")
    retire_link_tokens(PURPOSE, person.pk)
    token = issue_link_token(PURPOSE, person.pk, hours)
    send_email(
        "verify_email",
        person.email,
        name=person.name,
        link=build_link("/verify-email", token=token),
        expires_in=duration_text(hours, "hour"),
    )


@transaction.atomic
def verify_email(token):
    """Marks the person the link was issued for as verified. Whoever is signed in, if
    anyone, plays no part: the link alone decides whose email is confirmed."""
    person_id = consume_link_token(token, PURPOSE)
    confirmed = (
        CompanyUser.objects.filter(pk=person_id)
        .exclude(status=CompanyUser.Status.REMOVED)
        .update(email_verified=True)
    )
    if not confirmed:
        # The account is gone. Raising here also undoes the use of the link.
        raise link_refusal("link_invalid", "This link is not valid.")


def resend_verification(email):
    """Sends a new link when this email belongs to an active account that still needs one.
    The caller answers the same way either way, so nobody can learn which emails exist."""
    person = CompanyUser.objects.filter(
        email=email, email_verified=False, status=CompanyUser.Status.ACTIVE
    ).first()
    if person is not None:
        send_verification_email(person)
