from django.utils import timezone

from emailing.links import build_link
from emailing.rendering import format_moment
from emailing.service import send_email


def send_password_changed_email(person):
    """Tells the person their password changed, with a way back in if it was not them."""
    send_email(
        "password_changed",
        person.email,
        name=person.name,
        when=format_moment(timezone.now()),
        link=build_link("/forgot-password"),
    )


def send_email_changed_notice(person, previous_address):
    """Tells the person, at the address they had before, that the address was changed.

    The future email-change flow MUST call this once the new address has been saved, passing
    the address it replaced: a thief who changes the address also takes over the inbox that
    would warn the owner, so the notice goes to the old one. Nothing calls it yet because that
    flow does not exist."""
    send_email(
        "email_changed",
        previous_address,
        name=person.name,
        when=format_moment(timezone.now()),
        link=build_link("/contact"),
    )
