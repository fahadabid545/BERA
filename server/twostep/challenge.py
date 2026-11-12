"""The short step between a right password and a finished login.

After the password is right but before a session exists, the person holds a signed challenge
naming them and what it is for: giving a code, or setting two-step up. It carries no
credentials, expires, and cannot be used for the other purpose.
"""

from django.core import signing

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from core.errors import AppError
from platform_settings.service import get_setting
from signin.kinds import ADMIN, COMPANY

SALT = "bera.two-step.challenge"
SECONDS_PER_MINUTE = 60
VERIFY = "verify"
SETUP = "setup"

CHALLENGE_ENDED = "Your login took too long. Please log in again."


def _ended():
    return AppError("two_step_challenge_ended", CHALLENGE_ENDED, status_code=400)


def make_challenge(person, purpose, kind=COMPANY):
    return signing.dumps({"user": person.pk, "purpose": purpose, "kind": kind}, salt=SALT)


def _active_person(kind, user_id):
    if kind == ADMIN:
        return AdminUser.objects.filter(pk=user_id, status=AdminUser.Status.ACTIVE).first()
    person = (
        CompanyUser.objects.filter(pk=user_id, status=CompanyUser.Status.ACTIVE)
        .select_related("company")
        .first()
    )
    if person is None or person.company.status != Company.Status.ACTIVE:
        return None
    return person


def person_of_challenge(token, purpose, kind=COMPANY):
    """The person the challenge was made for, if it is genuine, current, for this purpose and
    this kind of sign-in (a company challenge never opens an admin login) and the person may
    still sign in."""
    try:
        claims = signing.loads(
            token, salt=SALT, max_age=get_setting("two_step.challenge_minutes") * SECONDS_PER_MINUTE
        )
    except signing.BadSignature as error:  # includes an expired signature
        raise _ended() from error
    if claims.get("purpose") != purpose or claims.get("kind") != kind:
        raise _ended()
    person = _active_person(kind, claims["user"])
    if person is None:
        raise _ended()
    # The state may have changed since the password step (two-step switched on or off).
    if (purpose == VERIFY) != person.two_step_enabled:
        raise _ended()
    return person
