"""Two-step verification with an authenticator app (TOTP) and one-time recovery codes."""

import hmac
import time

import pyotp
from django.db.models import Q

from companies.models import CompanyUser
from core.errors import AppError
from platform_settings.service import get_setting
from signin import guess_limit

from . import recovery_codes
from .models import RecoveryCode

ISSUER = "Bera"
STEP_SECONDS = 30  # the standard authenticator step; apps assume it
CODE_DIGITS = 6

WRONG_CODE = "That code is not correct. Try again."
LOST_DEVICE = (
    "Lost your device and your recovery codes? Contact support. "
    "We will check your identity before we can help."
)
ALREADY_ON = "Two-step verification is already on."
NOT_ON = "Two-step verification is not on."
REQUIRED_BY_COMPANY = "Your company requires two-step verification, so it cannot be turned off."
WRONG_PASSWORD = "Your password is incorrect."


def _wrong_code():
    return AppError("two_step_code_wrong", WRONG_CODE, status_code=400, fields={"code": WRONG_CODE})


def _refuse_wrong_code(person):
    """Counts the failure toward a pause of its own, apart from wrong passwords."""
    guess_limit.record_failure(person.email, _wrong_code(), scope=guess_limit.CODE_SCOPE)


def _current_step():
    return int(time.time()) // STEP_SECONDS


def _steps_to_try():
    drift = get_setting("two_step.code_drift_steps")
    return range(_current_step() - drift, _current_step() + drift + 1)


def _matching_step(person, code):
    """The 30-second step the code belongs to, or None. A step already used is not accepted
    again, so a code seen over a shoulder cannot be replayed."""
    totp = pyotp.TOTP(person.two_step_secret, digits=CODE_DIGITS, interval=STEP_SECONDS)
    for step in _steps_to_try():
        if hmac.compare_digest(totp.generate_otp(step), code):
            if person.two_step_last_step is None or step > person.two_step_last_step:
                return step
    return None


def _use_step(person, step):
    # Only moves forward, and only one of two simultaneous requests wins.
    claimed = (
        CompanyUser.objects.filter(pk=person.pk)
        .filter(Q(two_step_last_step__isnull=True) | Q(two_step_last_step__lt=step))
        .update(two_step_last_step=step)
    )
    return claimed == 1


def _looks_like_app_code(code):
    return len(code) == CODE_DIGITS and code.isdigit()


def check_code(person, code):
    """Accepts an app code or an unused recovery code, or raises the wrong-code answer."""
    guess_limit.refuse_if_paused(person.email, guess_limit.CODE_SCOPE)
    code = code.strip().replace(" ", "")
    if _looks_like_app_code(code):
        step = _matching_step(person, code)
        accepted = step is not None and _use_step(person, step)
    else:
        accepted = recovery_codes.use_code(person, code)
    if not accepted:
        _refuse_wrong_code(person)
    guess_limit.forget_failures(person.email, guess_limit.CODE_SCOPE)


def begin_setup(person):
    """Makes a fresh secret for the person's authenticator app. It does not count until
    `confirm_setup` has seen a right code."""
    if person.two_step_enabled:
        raise AppError("two_step_already_on", ALREADY_ON, status_code=409)
    person.two_step_secret = pyotp.random_base32()
    person.save(update_fields=["two_step_secret"])
    uri = pyotp.TOTP(person.two_step_secret).provisioning_uri(name=person.email, issuer_name=ISSUER)
    return {"secret": person.two_step_secret, "uri": uri}


def confirm_setup(person, code):
    """Switches two-step on once the app shows a right code. Returns the recovery codes, which
    are never shown again."""
    if person.two_step_enabled:
        raise AppError("two_step_already_on", ALREADY_ON, status_code=409)
    guess_limit.refuse_if_paused(person.email, guess_limit.CODE_SCOPE)
    code = code.strip().replace(" ", "")
    step = _matching_step(person, code) if person.two_step_secret else None
    if step is None or not _use_step(person, step):
        _refuse_wrong_code(person)
    guess_limit.forget_failures(person.email, guess_limit.CODE_SCOPE)
    person.two_step_enabled = True
    person.two_step_last_step = step
    person.save(update_fields=["two_step_enabled", "two_step_last_step"])
    return recovery_codes.replace_codes(person)


def turn_off(person, password, code):
    """Needs the password and a code, so a stolen session alone cannot switch it off."""
    if not person.two_step_enabled:
        raise AppError("two_step_not_on", NOT_ON, status_code=409)
    if person.company.require_two_step and person.role == CompanyUser.Role.MEMBER:
        raise AppError("two_step_required", REQUIRED_BY_COMPANY, status_code=403)
    guess_limit.refuse_if_paused(person.email)
    if not person.check_password(password):
        guess_limit.record_failure(
            person.email,
            AppError(
                "wrong_current_password",
                WRONG_PASSWORD,
                status_code=400,
                fields={"password": WRONG_PASSWORD},
            ),
        )
    guess_limit.forget_failures(person.email)
    check_code(person, code)
    person.two_step_enabled = False
    person.two_step_secret = ""
    person.two_step_last_step = None
    person.save(update_fields=["two_step_enabled", "two_step_secret", "two_step_last_step"])
    RecoveryCode.objects.filter(user=person).delete()


def status_of(person):
    return {
        "enabled": person.two_step_enabled,
        "recovery_codes_left": recovery_codes.codes_left(person) if person.two_step_enabled else 0,
        "required_by_company": person.company.require_two_step,
    }
