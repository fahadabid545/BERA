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
# Wrong passwords and wrong second-step codes are counted apart: a person who has the password
# must not be able to reset the count for code guesses by logging in again.
PASSWORD_SCOPE = "login"
CODE_SCOPE = "two-step"
# Admin logins are counted apart from company ones, even for the same address.
ADMIN_PASSWORD_SCOPE = "admin-login"
ADMIN_CODE_SCOPE = "admin-two-step"


def _failure_counter(scope):
    return f"{scope}_failures"


def account_subject(email, scope=PASSWORD_SCOPE):
    return f"{scope}-account:" + hashlib.sha256(email.encode("utf-8")).hexdigest()


def _pause_seconds():
    return get_setting("signin.lockout_minutes") * SECONDS_PER_MINUTE


def refuse_if_paused(email, scope=PASSWORD_SCOPE):
    """Even the right password is refused while paused, or guessing could carry on."""
    paused_for = rate_limits.seconds_blocked(account_subject(email, scope))
    if paused_for:
        raise Throttled(wait=paused_for)


def record_failure(email, refusal, scope=PASSWORD_SCOPE):
    """Counts a failed attempt and raises `refusal`; the one that reaches the limit pauses the
    account and raises the pause instead."""
    subject = account_subject(email, scope)
    window = get_setting("signin.attempt_window_minutes") * SECONDS_PER_MINUTE
    total = rate_limits.count_in_window(_failure_counter(scope), subject, window)
    if total >= get_setting("signin.max_failed_attempts"):
        rate_limits.block(subject, _pause_seconds(), why=f"{scope}_guesses")
        raise Throttled(wait=_pause_seconds())
    raise refusal


def forget_failures(email, scope=PASSWORD_SCOPE):
    rate_limits.forget_count(_failure_counter(scope), account_subject(email, scope))
