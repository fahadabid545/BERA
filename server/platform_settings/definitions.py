"""The complete list of platform settings: the single source of truth.

Each setting has a default and a rule for what values are allowed. Admins can
override values later (stored in the database); nothing else is hard-coded.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


def whole_number(minimum, maximum):
    def is_valid(value):
        # bool is a subclass of int, but True/False are not numbers here.
        return (
            isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum
        )

    return is_valid


def yes_or_no(value):
    return isinstance(value, bool)


def list_of_whole_numbers(minimum, maximum):
    is_number_valid = whole_number(minimum, maximum)

    def is_valid(value):
        return (
            isinstance(value, list)
            and len(value) > 0
            and len(set(value)) == len(value)
            and all(is_number_valid(item) for item in value)
        )

    return is_valid


def list_of_file_types(value):
    return (
        isinstance(value, list)
        and len(value) > 0
        and len(set(value)) == len(value)
        and all(isinstance(item, str) and item.isalnum() and item.islower() for item in value)
    )


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    default: Any
    is_valid: Callable[[Any], bool]


percent = whole_number(0, 100)

SETTINGS = [
    # Passwords
    SettingDefinition("passwords.min_length", 12, whole_number(8, 128)),
    SettingDefinition("passwords.block_common_passwords", True, yes_or_no),
    # Tokens and links
    SettingDefinition("tokens.access_minutes", 15, whole_number(1, 1440)),
    SettingDefinition("tokens.refresh_days", 7, whole_number(1, 90)),
    SettingDefinition("tokens.clock_leeway_seconds", 30, whole_number(0, 300)),
    SettingDefinition("tokens.refresh_attempts_per_minute", 10, whole_number(1, 1000)),
    SettingDefinition("tokens.email_verification_hours", 24, whole_number(1, 720)),
    SettingDefinition("tokens.password_reset_hours", 1, whole_number(1, 72)),
    SettingDefinition("tokens.team_invite_days", 7, whole_number(1, 90)),
    # Sign-in protection
    SettingDefinition("signin.max_failed_attempts", 5, whole_number(1, 100)),
    SettingDefinition("signin.attempt_window_minutes", 15, whole_number(1, 1440)),
    SettingDefinition("signin.lockout_minutes", 15, whole_number(1, 1440)),
    # Team
    SettingDefinition("team.max_accounts_per_company", 3, whole_number(1, 1000)),
    # Uploads
    SettingDefinition("uploads.allowed_file_types", ["pdf", "docx"], list_of_file_types),
    SettingDefinition("uploads.max_file_size_mb", 10, whole_number(1, 100)),
    SettingDefinition("uploads.max_files_per_batch", 50, whole_number(1, 500)),
    SettingDefinition("uploads.cv_pages_read", 15, whole_number(1, 200)),
    # Request limits: forms stay small, only uploads may be large (see uploads.* above)
    SettingDefinition("requests.max_form_kilobytes", 256, whole_number(1, 4096)),
    SettingDefinition("requests.max_file_name_characters", 150, whole_number(10, 255)),
    # Job descriptions and requirements
    SettingDefinition("jobs.description_max_characters", 15000, whole_number(100, 100000)),
    SettingDefinition("jobs.max_requirements_per_project", 30, whole_number(1, 200)),
    # Data retention
    SettingDefinition("retention.choices_days", [30, 90, 180, 365], list_of_whole_numbers(1, 3650)),
    SettingDefinition("retention.default_days", 180, whole_number(1, 3650)),
    # Sharing and downloads
    SettingDefinition(
        "sharing.report_link_choices_days", [1, 7, 30], list_of_whole_numbers(1, 365)
    ),
    SettingDefinition("sharing.report_link_default_days", 7, whole_number(1, 365)),
    SettingDefinition("sharing.download_package_link_hours", 24, whole_number(1, 720)),
    # Usage and account lifecycle
    SettingDefinition("usage.warning_percents", [80, 100], list_of_whole_numbers(1, 100)),
    SettingDefinition("billing.past_due_grace_days", 7, whole_number(0, 90)),
    SettingDefinition("account.deletion_grace_days", 14, whole_number(0, 365)),
    # Scoring
    SettingDefinition("scoring.must_have_weight_percent", 70, percent),
    SettingDefinition("scoring.nice_to_have_weight_percent", 30, percent),
    SettingDefinition("scoring.top_n", 10, whole_number(1, 1000)),
    SettingDefinition("scoring.grade_a_min", 85, percent),
    SettingDefinition("scoring.grade_b_min", 70, percent),
    SettingDefinition("scoring.grade_c_min", 55, percent),
    SettingDefinition("scoring.grade_d_min", 40, percent),
    SettingDefinition("scoring.strong_match_min", 75, percent),
    SettingDefinition("scoring.possible_match_min", 55, percent),
    # Live screen updates
    SettingDefinition("live_updates.max_delay_seconds", 3, whole_number(1, 60)),
]

DEFINITIONS = {definition.key: definition for definition in SETTINGS}
