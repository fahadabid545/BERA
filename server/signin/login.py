"""Checking an email and password, and pausing an account that is being guessed at.

Everything a wrong guess can tell an attacker is kept the same: an email that does not exist,
a wrong password, a blocked person and a removed one all get one message, take the same
time (a password is always hashed and compared) and count the same toward the pause.
Only someone who has the right password is told more (unverified email, suspended company).
"""

import functools
import hashlib

from django.contrib.auth.hashers import check_password, is_password_usable, make_password
from rest_framework.exceptions import Throttled

from companies.models import Company, CompanyUser
from core import rate_limits
from core.errors import AppError
from core.field_protection import normalize_email
from platform_settings.service import get_setting

SECONDS_PER_MINUTE = 60
FAILED_ATTEMPTS = "login_failures"

WRONG_CREDENTIALS = "Email or password is incorrect."
VERIFY_EMAIL_FIRST = "Please verify your email"
COMPANY_SUSPENDED = "Your company account is suspended. Please contact support."


def _wrong_credentials():
    return AppError("invalid_credentials", WRONG_CREDENTIALS, status_code=400)


@functools.cache
def _stand_in_hash():
    # Compared against when there is nobody to check, so the work (and the time) is the same.
    return make_password("a password nobody has")


def _account_subject(email):
    return "login-account:" + hashlib.sha256(email.encode("utf-8")).hexdigest()


def _password_matches(person, password):
    usable = person is not None and is_password_usable(person.password_hash)
    longest = get_setting("passwords.max_length")
    if usable and len(password) <= longest:
        return check_password(password, person.password_hash)
    check_password(password[:longest], _stand_in_hash())
    return False


def _pause_seconds():
    return get_setting("signin.lockout_minutes") * SECONDS_PER_MINUTE


def _fail(subject):
    """Counts a failed attempt; the one that reaches the limit pauses the account."""
    window = get_setting("signin.attempt_window_minutes") * SECONDS_PER_MINUTE
    total = rate_limits.count_in_window(FAILED_ATTEMPTS, subject, window)
    if total >= get_setting("signin.max_failed_attempts"):
        rate_limits.block(subject, _pause_seconds())
        raise Throttled(wait=_pause_seconds())
    raise _wrong_credentials()


def check_login(email, password):
    """The company user who may now be signed in, or an error saying why not."""
    email = normalize_email(email)
    subject = _account_subject(email)
    paused_for = rate_limits.seconds_blocked(subject)
    if paused_for:
        # Even the right password is refused while paused, or guessing could carry on.
        raise Throttled(wait=paused_for)

    person = CompanyUser.objects.filter(email=email).select_related("company").first()
    password_ok = _password_matches(person, password)
    if not password_ok or person.status != CompanyUser.Status.ACTIVE:
        _fail(subject)

    # From here the password was right, so saying more is no help to a guesser.
    rate_limits.forget_count(FAILED_ATTEMPTS, subject)
    if person.company.status == Company.Status.SUSPENDED:
        raise AppError("company_suspended", COMPANY_SUSPENDED, status_code=403)
    if not person.email_verified:
        raise AppError("email_not_verified", VERIFY_EMAIL_FIRST, status_code=403)
    return person
