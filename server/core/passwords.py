"""The password rules, the same everywhere a password is chosen: sign up, reset, invite, profile."""

import functools
from collections.abc import Callable
from dataclasses import dataclass

from django.contrib.auth.password_validation import CommonPasswordValidator
from rest_framework import serializers

from platform_settings.service import get_setting


@functools.cache
def _common_passwords():
    # Django ships a list of the 20,000 most used passwords.
    return CommonPasswordValidator().passwords


@dataclass(frozen=True)
class PasswordRule:
    id: str
    describe: Callable[[], str]  # shown as a live hint: "At least 12 characters"
    problem: Callable[[], str]  # shown when the rule is broken: "Use at least 12 characters."
    is_met: Callable[[str], bool]
    applies: Callable[[], bool] = lambda: True


RULES = (
    PasswordRule(
        "min_length",
        lambda: f"At least {get_setting('passwords.min_length')} characters",
        lambda: f"Use at least {get_setting('passwords.min_length')} characters.",
        lambda password: len(password) >= get_setting("passwords.min_length"),
    ),
    PasswordRule(
        "max_length",
        lambda: f"At most {get_setting('passwords.max_length')} characters",
        lambda: f"Use at most {get_setting('passwords.max_length')} characters.",
        lambda password: len(password) <= get_setting("passwords.max_length"),
    ),
    PasswordRule(
        "not_common",
        lambda: "Not a commonly used password",
        lambda: "This password is too common. Choose one that is harder to guess.",
        lambda password: password.lower().strip() not in _common_passwords(),
        applies=lambda: get_setting("passwords.block_common_passwords"),
    ),
)


def password_rule_results(password):
    """Each rule with whether this password meets it: the live hints while typing."""
    return [
        {"id": rule.id, "text": rule.describe(), "met": rule.is_met(password)}
        for rule in RULES
        if rule.applies()
    ]


def password_problems(password):
    """Every reason this password is refused, in words for the person; empty when it is fine."""
    return [rule.problem() for rule in RULES if rule.applies() and not rule.is_met(password)]


class PasswordTextField(serializers.CharField):
    """A password exactly as typed (spaces count), as text and never echoed back."""

    def __init__(self, **kwargs):
        super().__init__(write_only=True, trim_whitespace=False, allow_blank=True, **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class PasswordField(PasswordTextField):
    """A new password, checked against the rules."""

    def run_validation(self, data=serializers.empty):
        value = super().run_validation(data)
        problems = password_problems(value)
        if problems:
            raise serializers.ValidationError(" ".join(problems))
        return value
