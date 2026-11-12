"""Checking an admin's email and password. Wrong guesses are handled as for company logins:
one message for every reason, the same time taken, and a pause after too many."""

from core.errors import AppError
from core.field_protection import normalize_email
from signin import guess_limit
from signin.login import WRONG_CREDENTIALS, password_matches

from .models import AdminUser

SCOPE = guess_limit.ADMIN_PASSWORD_SCOPE


def check_admin_login(email, password):
    """The admin who may go on to the two-step check, or an error."""
    email = normalize_email(email)
    guess_limit.refuse_if_paused(email, SCOPE)
    person = AdminUser.objects.filter(email=email).first()
    if not password_matches(person, password) or person.status != AdminUser.Status.ACTIVE:
        guess_limit.record_failure(
            email, AppError("invalid_credentials", WRONG_CREDENTIALS, status_code=400), scope=SCOPE
        )
    guess_limit.forget_failures(email, SCOPE)
    return person
