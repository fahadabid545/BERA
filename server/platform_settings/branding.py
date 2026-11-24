"""The platform's name and support address, read when they are used so a change applies at once.
Emails and the messages that tell a person to contact support use these and never write the name
or the address themselves (a test fails if they come back)."""

from .service import get_setting


def app_name():
    return get_setting("general.app_name")


def support_email():
    return get_setting("general.support_email")


def contact_support(sentence="Please contact support"):
    """ "Please contact support at support@example.test." """
    return f"{sentence} at {support_email()}."
