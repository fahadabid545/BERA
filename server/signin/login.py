"""Checking an email and password, and pausing an account that is being guessed at.

Everything a wrong guess can tell an attacker is kept the same: an email that does not exist,
a wrong password, a blocked person and a removed one all get one message, take the same
time (a password is always hashed and compared) and count the same toward the pause.
Only someone who has the right password is told more (unverified email, suspended company).
"""

import functools

from django.contrib.auth.hashers import check_password, is_password_usable, make_password

from companies.models import Company, CompanyUser
from core.errors import AppError
from core.field_protection import normalize_email
from platform_settings.service import get_setting

from . import guess_limit

WRONG_CREDENTIALS = "Email or password is incorrect."
VERIFY_EMAIL_FIRST = "Please verify your email"
COMPANY_SUSPENDED = "Your company account is suspended. Please contact support."


def _wrong_credentials():
    return AppError("invalid_credentials", WRONG_CREDENTIALS, status_code=400)


@functools.cache
def _stand_in_hash():
    # Compared against when there is nobody to check, so the work (and the time) is the same.
    return make_password("a password nobody has")


def _password_matches(person, password):
    usable = person is not None and is_password_usable(person.password_hash)
    longest = get_setting("passwords.max_length")
    if usable and len(password) <= longest:
        return check_password(password, person.password_hash)
    check_password(password[:longest], _stand_in_hash())
    return False


def check_login(email, password):
    """The company user who may now be signed in, or an error saying why not."""
    email = normalize_email(email)
    guess_limit.refuse_if_paused(email)

    person = CompanyUser.objects.filter(email=email).select_related("company").first()
    password_ok = _password_matches(person, password)
    if not password_ok or person.status != CompanyUser.Status.ACTIVE:
        guess_limit.record_failure(email, _wrong_credentials())

    # From here the password was right, so saying more is no help to a guesser.
    guess_limit.forget_failures(email)
    if person.company.status == Company.Status.SUSPENDED:
        raise AppError("company_suspended", COMPANY_SUSPENDED, status_code=403)
    if not person.email_verified:
        raise AppError("email_not_verified", VERIFY_EMAIL_FIRST, status_code=403)
    return person
