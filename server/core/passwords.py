"""The password rules, the same everywhere a password is chosen: sign up, reset, invite, profile."""

import functools

from django.contrib.auth.password_validation import CommonPasswordValidator
from rest_framework import serializers

from platform_settings.service import get_setting


@functools.cache
def _common_passwords():
    # Django ships a list of the 20,000 most used passwords.
    return CommonPasswordValidator().passwords


def password_problems(password):
    """Every reason this password is refused, in words for the person; empty when it is fine."""
    problems = []
    minimum, maximum = get_setting("passwords.min_length"), get_setting("passwords.max_length")
    if len(password) < minimum:
        problems.append(f"Use at least {minimum} characters.")
    if len(password) > maximum:
        problems.append(f"Use at most {maximum} characters.")
    if get_setting("passwords.block_common_passwords") and (
        password.lower().strip() in _common_passwords()
    ):
        problems.append("This password is too common. Choose one that is harder to guess.")
    return problems


class PasswordField(serializers.CharField):
    """A password exactly as typed (spaces count), checked against the rules."""

    def __init__(self, **kwargs):
        super().__init__(write_only=True, trim_whitespace=False, allow_blank=True, **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)

    def run_validation(self, data=serializers.empty):
        value = super().run_validation(data)
        problems = password_problems(value)
        if problems:
            raise serializers.ValidationError(" ".join(problems))
        return value
