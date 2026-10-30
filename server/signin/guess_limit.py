"""Pausing an account whose password is being guessed.

Wrong guesses at the login page and wrong "current password" entries on the profile page
count together, per account (whether or not the account exists), so the profile page cannot
be used to guess around the pause.
"""

import hashlib

from rest_framework.exceptions import Throttled

from core import rate_limits
from platform_settings.service import get_setting

SECONDS_PER_MINUTE = 60
FAILED_ATTEMPTS = "login_failures"


def account_subject(email):
    return "login-account:" + hashlib.sha256(email.encode("utf-8")).hexdigest()


def _pause_seconds():
    return get_setting("signin.lockout_minutes") * SECONDS_PER_MINUTE


def refuse_if_paused(email):
    """Even the right password is refused while paused, or guessing could carry on."""
    paused_for = rate_limits.seconds_blocked(account_subject(email))
    if paused_for:
        raise Throttled(wait=paused_for)


def record_failure(email, refusal):
    """Counts a failed attempt and raises `refusal`; the one that reaches the limit pauses the
    account and raises the pause instead."""
    subject = account_subject(email)
    window = get_setting("signin.attempt_window_minutes") * SECONDS_PER_MINUTE
    total = rate_limits.count_in_window(FAILED_ATTEMPTS, subject, window)
    if total >= get_setting("signin.max_failed_attempts"):
        rate_limits.block(subject, _pause_seconds())
        raise Throttled(wait=_pause_seconds())
    raise refusal


def forget_failures(email):
    rate_limits.forget_count(FAILED_ATTEMPTS, account_subject(email))
