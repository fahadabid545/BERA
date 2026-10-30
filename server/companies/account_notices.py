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
