import pytest

from platform_settings.definitions import SETTINGS, list_of_file_types, whole_number

# The values the platform ships with. If a default changes on purpose, this
# list is the specification that must be updated with it.
EXPECTED_DEFAULTS = {
    "passwords.min_length": 12,
    "passwords.block_common_passwords": True,
    "passwords.max_length": 128,
    "tokens.access_minutes": 15,
    "tokens.refresh_days": 7,
    "tokens.clock_leeway_seconds": 30,
    "tokens.email_verification_hours": 24,
    "email.retry_waits_seconds": [60, 300, 1800],
    "tokens.password_reset_hours": 1,
    "tokens.team_invite_days": 7,
    "signin.max_failed_attempts": 5,
    "signin.attempt_window_minutes": 15,
    "signin.lockout_minutes": 15,
    "rate_limits.login_per_minute": 10,
    "rate_limits.refresh_per_minute": 30,
    "rate_limits.sign_up_per_hour": 5,
    "rate_limits.sign_up_notices_per_hour": 3,
    "rate_limits.verification_resend_per_hour": 3,
    "rate_limits.password_reset_per_hour": 5,
    "rate_limits.invites_per_hour": 20,
    "rate_limits.upload_files_per_10_minutes": 100,
    "rate_limits.downloads_per_minute": 60,
    "rate_limits.contact_per_hour": 3,
    "rate_limits.other_requests_per_minute": 120,
    "rate_limits.violations_before_block": 5,
    "rate_limits.violation_window_minutes": 10,
    "rate_limits.block_minutes": 15,
    "team.max_accounts_per_company": 3,
    "uploads.allowed_file_types": ["pdf", "docx"],
    "uploads.max_file_size_mb": 10,
    "uploads.max_files_per_batch": 50,
    "uploads.cv_pages_read": 15,
    "requests.max_form_kilobytes": 256,
    "requests.max_file_name_characters": 150,
    "jobs.description_max_characters": 15000,
    "jobs.max_requirements_per_project": 30,
    "retention.choices_days": [30, 90, 180, 365],
    "retention.default_days": 180,
    "sharing.report_link_choices_days": [1, 7, 30],
    "sharing.report_link_default_days": 7,
    "sharing.download_package_link_hours": 24,
    "usage.warning_percents": [80, 100],
    "billing.past_due_grace_days": 7,
    "account.deletion_grace_days": 14,
    "scoring.must_have_weight_percent": 70,
    "scoring.nice_to_have_weight_percent": 30,
    "scoring.top_n": 10,
    "scoring.grade_a_min": 85,
    "scoring.grade_b_min": 70,
    "scoring.grade_c_min": 55,
    "scoring.grade_d_min": 40,
    "scoring.strong_match_min": 75,
    "scoring.possible_match_min": 55,
    "live_updates.max_delay_seconds": 3,
}


def test_every_default_is_allowed_by_its_own_rule():
    for definition in SETTINGS:
        assert definition.is_valid(definition.default), definition.key


def test_setting_names_are_unique():
    keys = [definition.key for definition in SETTINGS]
    assert len(keys) == len(set(keys))


def test_every_setting_from_the_ticket_exists_with_its_default():
    actual = {definition.key: definition.default for definition in SETTINGS}
    assert actual == EXPECTED_DEFAULTS


def test_retention_and_sharing_defaults_are_among_their_choices():
    defaults = {definition.key: definition.default for definition in SETTINGS}
    assert defaults["retention.default_days"] in defaults["retention.choices_days"]
    assert (
        defaults["sharing.report_link_default_days"] in defaults["sharing.report_link_choices_days"]
    )


@pytest.mark.parametrize("value", ["12", 12.0, True, None, [12], 7, 129])
def test_whole_number_rejects_wrong_type_and_out_of_range(value):
    assert whole_number(8, 128)(value) is False


@pytest.mark.parametrize("value", [[], "pdf", ["PDF"], ["pdf", "pdf"], ["pdf", 1], ["p df"]])
def test_file_type_list_rejects_bad_values(value):
    assert list_of_file_types(value) is False
