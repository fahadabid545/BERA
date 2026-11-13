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


def short_text(maximum):
    def is_valid(value):
        return isinstance(value, str) and 0 < len(value.strip()) <= maximum

    return is_valid


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
    # Long passwords are slow to hash; this keeps a huge one from tying the server up.
    SettingDefinition("passwords.max_length", 128, whole_number(12, 1024)),
    # Tokens and links
    SettingDefinition("tokens.access_minutes", 15, whole_number(1, 1440)),
    SettingDefinition("tokens.refresh_days", 7, whole_number(1, 90)),
    # Admin sessions are shorter than company ones: an admin can see every company.
    # Security alerts to the super admins: one email per kind of event per cooldown, and the
    # number of CV downloads by one user in the window that counts as unusual.
    SettingDefinition("security.alert_cooldown_minutes", 60, whole_number(1, 1440)),
    SettingDefinition("security.download_alert_window_minutes", 60, whole_number(1, 1440)),
    SettingDefinition("security.download_alert_threshold", 200, whole_number(1, 100000)),
    SettingDefinition("tokens.admin_access_minutes", 10, whole_number(1, 1440)),
    SettingDefinition("tokens.admin_refresh_hours", 8, whole_number(1, 168)),
    SettingDefinition("tokens.clock_leeway_seconds", 30, whole_number(0, 300)),
    SettingDefinition("tokens.email_verification_hours", 24, whole_number(1, 720)),
    SettingDefinition("tokens.password_reset_hours", 1, whole_number(1, 72)),
    SettingDefinition("tokens.team_invite_days", 7, whole_number(1, 90)),
    # Email: how long to wait before each new attempt when the provider fails. The number
    # of entries is the number of retries.
    SettingDefinition(
        "email.retry_waits_seconds", [60, 300, 1800], list_of_whole_numbers(1, 86400)
    ),
    # Sign-in protection
    SettingDefinition("signin.max_failed_attempts", 5, whole_number(1, 100)),
    SettingDefinition("signin.attempt_window_minutes", 15, whole_number(1, 1440)),
    SettingDefinition("signin.lockout_minutes", 15, whole_number(1, 1440)),
    # Two-step verification
    SettingDefinition("two_step.recovery_code_count", 10, whole_number(1, 50)),
    # Codes from this many 30-second steps before and after now are accepted (clock drift).
    SettingDefinition("two_step.code_drift_steps", 1, whole_number(0, 5)),
    # How long a person has, after the password, to give the code or finish setting up.
    SettingDefinition("two_step.challenge_minutes", 10, whole_number(1, 60)),
    # Rate limits. Counts per window; "address" means the visitor's real network address.
    SettingDefinition("rate_limits.login_per_minute", 10, whole_number(1, 10000)),
    SettingDefinition("rate_limits.refresh_per_minute", 30, whole_number(1, 10000)),
    SettingDefinition("rate_limits.sign_up_per_hour", 5, whole_number(1, 10000)),
    # Notices sent to one email address because someone tried to sign up with it.
    SettingDefinition("rate_limits.sign_up_notices_per_hour", 3, whole_number(1, 10000)),
    SettingDefinition("rate_limits.verification_resend_per_hour", 3, whole_number(1, 10000)),
    SettingDefinition("rate_limits.password_reset_per_hour", 5, whole_number(1, 10000)),
    SettingDefinition("rate_limits.invites_per_hour", 20, whole_number(1, 10000)),
    SettingDefinition("rate_limits.upload_files_per_10_minutes", 100, whole_number(1, 100000)),
    SettingDefinition("rate_limits.downloads_per_minute", 60, whole_number(1, 10000)),
    SettingDefinition("rate_limits.contact_per_hour", 3, whole_number(1, 10000)),
    SettingDefinition("rate_limits.other_requests_per_minute", 120, whole_number(1, 100000)),
    # Repeated abuse: this many refused requests within the window block the source.
    SettingDefinition("rate_limits.violations_before_block", 5, whole_number(1, 1000)),
    SettingDefinition("rate_limits.violation_window_minutes", 10, whole_number(1, 1440)),
    SettingDefinition("rate_limits.block_minutes", 15, whole_number(1, 1440)),
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
    SettingDefinition("activity.page_size", 50, whole_number(1, 500)),
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
    # Projects. The reading model and prompt version are pinned to each new project; the
    # stand-in values are replaced from the admin panel once Model settings and Prompt
    # versions exist.
    SettingDefinition("projects.page_size", 20, whole_number(1, 200)),
    SettingDefinition("projects.title_max_length", 120, whole_number(10, 500)),
    SettingDefinition("projects.description_max_length", 15000, whole_number(500, 100000)),
    SettingDefinition("projects.short_description_length", 300, whole_number(1, 5000)),
    SettingDefinition("ai.reading_model", "standin-reading-model", short_text(100)),
    SettingDefinition("ai.prompt_version", "standin-prompt-v1", short_text(100)),
    # Live screen updates
    SettingDefinition("live_updates.max_delay_seconds", 3, whole_number(1, 60)),
]

DEFINITIONS = {definition.key: definition for definition in SETTINGS}
