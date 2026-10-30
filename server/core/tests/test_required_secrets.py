import pytest

from config.secrets import REQUIRED_SETTINGS, check_required_settings, looks_like_placeholder
from core.errors import ConfigurationError
from core.tests.test_settings_per_environment import FAKE_VALUES, load_settings

REAL = {
    "DJANGO_SECRET_KEY": "test-only-django-secret-key-0000-1111-2222",
    "DATABASE_URL": "postgres://app:test-only-db-pw-3141592653@127.0.0.1:5432/bera",
    "JWT_COMPANY_SECRET": "test-only-company-signing-key-3a9f1c7e5b",
    "JWT_ADMIN_SECRET": "test-only-admin-signing-key-8d2e6b4f0a",
    "TRUSTED_PROXY_COUNT": "1",
}
ENVIRONMENTS = ["staging", "production"]


def refusal(environ, app_env):
    with pytest.raises(ConfigurationError) as caught:
        check_required_settings(environ, app_env)
    return caught.value


def test_the_list_holds_exactly_what_exists_today():
    assert {setting.name for setting in REQUIRED_SETTINGS} == set(REAL)


@pytest.mark.parametrize("app_env", ENVIRONMENTS)
def test_real_values_pass(app_env):
    check_required_settings(REAL, app_env)


@pytest.mark.parametrize("app_env", ENVIRONMENTS)
@pytest.mark.parametrize("name", REAL)
def test_a_missing_setting_stops_staging_and_production(name, app_env):
    error = refusal({**REAL, name: " "}, app_env)
    assert error.details == {"missing": [name], "placeholders": []}


def test_every_missing_setting_is_listed_at_once():
    error = refusal({}, "production")
    assert error.details["missing"] == [setting.name for setting in REQUIRED_SETTINGS]


@pytest.mark.parametrize("app_env", ENVIRONMENTS)
@pytest.mark.parametrize("name", ["DJANGO_SECRET_KEY", "JWT_COMPANY_SECRET", "JWT_ADMIN_SECRET"])
@pytest.mark.parametrize(
    "placeholder",
    [
        "fake-dev-only-secret-key",
        "changeme-changeme-changeme-changeme",
        "your-secret-key-goes-here-please",
        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "aaaaaaaabbbbbbbbaaaaaaaabbbbbbbb",
        "short",
        "REPLACE_ME_WITH_A_REAL_SECRET_VALUE",
    ],
)
def test_a_placeholder_secret_stops_staging_and_production(name, placeholder, app_env):
    error = refusal({**REAL, name: placeholder}, app_env)
    assert error.details == {"missing": [], "placeholders": [name]}


@pytest.mark.parametrize(
    "database_url",
    [
        "postgres://bera:fake-dev-db-password@127.0.0.1:5432/bera",
        "postgres://bera:changeme@127.0.0.1:5432/bera",  # nosecret: a placeholder on purpose
        "postgres://bera@127.0.0.1:5432/bera",
        "postgres://bera:@127.0.0.1:5432/bera",
    ],
)
def test_a_database_address_with_a_placeholder_or_no_password_is_refused(database_url):
    error = refusal({**REAL, "DATABASE_URL": database_url}, "production")
    assert error.details["placeholders"] == ["DATABASE_URL"]


def test_the_proxy_count_is_required_but_is_not_a_secret():
    check_required_settings({**REAL, "TRUSTED_PROXY_COUNT": "0"}, "production")
    assert refusal({**REAL, "TRUSTED_PROXY_COUNT": ""}, "production").details["missing"] == [
        "TRUSTED_PROXY_COUNT"
    ]


def test_development_may_use_fake_values_and_skip_the_proxy_count():
    fake = {
        "DJANGO_SECRET_KEY": "fake-dev-only-secret-key",
        "DATABASE_URL": "postgres://bera:fake-dev-db-password@127.0.0.1:5432/bera",
        "JWT_COMPANY_SECRET": "fake-dev-only-company-signing-secret-0001",
        "JWT_ADMIN_SECRET": "fake-dev-only-admin-signing-secret-00002",
    }
    check_required_settings(fake, "development")


def test_development_still_needs_the_secrets_to_exist():
    assert refusal({}, "development").details["missing"] == [
        "DJANGO_SECRET_KEY",
        "DATABASE_URL",
        "JWT_COMPANY_SECRET",
        "JWT_ADMIN_SECRET",
    ]


@pytest.mark.parametrize("value", ["fake", "Password123", "CHANGEME", "aaaa", " "])
def test_obvious_placeholders_are_recognised(value):
    assert looks_like_placeholder(value)


def test_a_random_looking_value_is_not_a_placeholder():
    assert not looks_like_placeholder("Zk3vQ8mT1xRb7LwN4pYc9HsJ2dGfA6eU")


@pytest.mark.parametrize("name", ["DJANGO_SECRET_KEY", "JWT_ADMIN_SECRET", "DATABASE_URL"])
def test_the_refusal_never_contains_a_secret_value(name):
    leaked = "fake-leak-check-value-must-never-show-up"
    environ = {**REAL, name: leaked if name != "DATABASE_URL" else f"postgres://u:{leaked}@h/db"}  # nosecret: built from a fake value
    error = refusal(environ, "production")
    assert leaked not in error.message and leaked not in str(error.details)


@pytest.mark.parametrize("app_env", ENVIRONMENTS)
def test_a_real_start_is_refused_with_a_placeholder_and_prints_no_value(app_env):
    result = load_settings(app_env, DJANGO_SECRET_KEY="fake-dev-only-secret-key")
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr and "placeholders" in result.stderr
    assert "fake-dev-only-secret-key" not in result.stderr


def test_the_test_values_used_to_start_the_app_are_real_looking():
    assert not any(
        looks_like_placeholder(value)
        for name, value in FAKE_VALUES.items()
        if name in {"DJANGO_SECRET_KEY", "JWT_COMPANY_SECRET", "JWT_ADMIN_SECRET"}
    )
