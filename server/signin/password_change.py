"""A signed-in person chooses a new password, proving they know the current one."""

from companies.account_notices import send_password_changed_email
from companies.password_reset import SAME_PASSWORD
from core.errors import AppError, form_error
from core.passwords import password_problems

from . import guess_limit

WRONG_CURRENT_PASSWORD = "Your current password is incorrect."


def change_password(person, current_password, new_password, confirm_password):
    """Saving the new password ends every session of the person (see signals.py); the caller
    then starts a fresh one for the device in use.

    The current password is checked first and a wrong one gets that one plain message, with
    no hints about the new password. Wrong entries count toward the same pause as wrong
    guesses at the login page."""
    guess_limit.refuse_if_paused(person.email)
    if not person.check_password(current_password):
        guess_limit.record_failure(
            person.email,
            AppError(
                "wrong_current_password",
                WRONG_CURRENT_PASSWORD,
                status_code=400,
                fields={"current_password": WRONG_CURRENT_PASSWORD},
            ),
        )
    guess_limit.forget_failures(person.email)

    problems = password_problems(new_password)
    if problems:
        raise form_error({"password": " ".join(problems)})
    if new_password != confirm_password:
        raise form_error({"confirm_password": "The passwords do not match."})
    if person.check_password(new_password):
        raise form_error({"password": SAME_PASSWORD})

    person.set_password(new_password)
    person.save()
    send_password_changed_email(person)
