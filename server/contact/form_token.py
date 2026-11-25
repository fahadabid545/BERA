"""The signed moment a contact form was opened.

The server signs the time when it hands out the form, so a bot cannot invent one. A message
sent sooner than a person could type it, later than the maximum age, or with a missing or
altered token is treated as spam. The token holds nothing about the visitor.
"""

import time

from django.core import signing

from platform_settings.service import get_setting

SALT = "contact-form-opened"

REFRESH_AT_FRACTION_OF_MAX_AGE = 0.8

TOO_FAST = "too_fast"
EXPIRED = "expired"
INVALID = "invalid"


def issue():
    return signing.dumps({"opened_at": int(time.time())}, salt=SALT)


def refresh_after_seconds():
    return int(get_setting("contact.form_max_age_seconds") * REFRESH_AT_FRACTION_OF_MAX_AGE)


def problem_with(token):
    """None when the token is fine, otherwise why the message looks like spam."""
    try:
        opened_at = signing.loads(token, salt=SALT)["opened_at"]
    except (signing.BadSignature, KeyError, TypeError):
        return INVALID
    age = time.time() - opened_at
    if age < get_setting("contact.min_fill_seconds"):
        return TOO_FAST
    if age > get_setting("contact.form_max_age_seconds"):
        return EXPIRED
    return None
