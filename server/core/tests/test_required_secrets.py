import pytest

from config.secrets import REQUIRED_SETTINGS, check_required_settings, looks_like_placeholder
from core.errors import ConfigurationError
from core.tests.test_settings_per_environment import FAKE_VALUES, load_settings

REAL = {
    "DJANGO_SECRET_KEY": "test-only-django-secret-key-0000-1111-2222",
    "DATABASE_URL": "postgres://app:test-only-db-pw-3141592653@127.0.0.1:5432/bera",
    "MIGRATION_DATABASE_URL": "postgres://migrator:test-only-migrator-pw-2718281828@127.0.0.1:5432/bera",  # nosecret: fake
    "FIELD_ENCRYPTION_KEY": "test-only-field-encryption-key-7c1d9e",
    "FIELD_HASH_KEY": "test-only-field-hash-key-4b8a2f6d03",
    "EMAIL_HOST": "smtp.example.com",
    "EMAIL_HOST_USER": "smtp-user-test",
    "EMAIL_HOST_PASSWORD": "test-only-smtp-key-9d3b1f7a52c4",
    "EMAIL_FROM_ADDRESS": "bera@example.com",
    "WEB_BASE_URL": "https://app.example.com",
    "JWT_COMPANY_SECRET": "test-only-company-signing-key-3a9f1c7e5b",
    "JWT_ADMIN_SECRET": "test-only-admin-signing-key-8d2e6b4f0a",
    "TRUSTED_PROXY_COUNT": "1",
}
ENVIRONMENTS = ["staging", "production"]
# The migrator's address is held only by the process that changes the structure.
APP_SETTINGS = [name for name in REAL if name != "MIGRATION_DATABASE_URL"]
MIGRATION_SETTINGS = [name for name in REAL if name != "DATABASE_URL"]


def refusal(environ, app_env, role="app"):
    with pytest.raises(ConfigurationError) as caught:
        check_required_settings(environ, app_env, role)
    return caught.value


APP_SETTINGS_IN_ORDER = [setting.name for setting in REQUIRED_SETTINGS if "app" in setting.roles]


def test_the_list_holds_exactly_what_exists_today():
    assert {setting.name for setting in REQUIRED_SETTINGS} == set(REAL)


@pytest.mark.parametrize("app_env", ENVIRONMENTS)
def test_real_values_pass(app_env):
    check_required_settings(REAL, app_env)


@pytest.mark.parametrize("app_env", ENVIRONMENTS)
@pytest.mark.parametrize("name", APP_SETTINGS)
def test_a_missing_setting_stops_staging_and_production(name, app_env):
    error = refusal({**REAL, name: " "}, app_env)
    assert error.details == {"missing": [name], "placeholders": []}


def test_every_missing_setting_is_listed_at_once():
    error = refusal({}, "production")
    assert error.details["missing"] == APP_SETTINGS_IN_ORDER


def test_the_app_never_needs_the_migrator_password_and_the_migrator_never_the_apps():
    only_app = {name: value for name, value in REAL.items() if name != "MIGRATION_DATABASE_URL"}
    only_migrator = {name: value for name, value in REAL.items() if name != "DATABASE_URL"}
    check_required_settings(only_app, "production", "app")
    check_required_settings(only_migrator, "production", "migrations")
    assert refusal(only_app, "production", "migrations").details["missing"] == [
        "MIGRATION_DATABASE_URL"
    ]
    assert refusal(only_migrator, "production", "app").details["missing"] == ["DATABASE_URL"]


@pytest.mark.parametrize("name", MIGRATION_SETTINGS)
def test_a_missing_setting_stops_the_migration_process_too(name):
    error = refusal({**REAL, name: ""}, "production", "migrations")
    assert error.details == {"missing": [name], "placeholders": []}


def test_a_placeholder_password_in_the_migrator_address_is_refused():
    address = "postgres://migrator:changeme@127.0.0.1:5432/bera"  # nosecret: a placeholder
    error = refusal({**REAL, "MIGRATION_DATABASE_URL": address}, "production", "migrations")
    assert error.details["placeholders"] == ["MIGRATION_DATABASE_URL"]


@pytest.mark.parametrize("app_env", ENVIRONMENTS)
@pytest.mark.parametrize(
    "name",
    [
        "DJANGO_SECRET_KEY",
        "JWT_COMPANY_SECRET",
        "JWT_ADMIN_SECRET",
        "FIELD_ENCRYPTION_KEY",
        "FIELD_HASH_KEY",
        "EMAIL_HOST_PASSWORD",
    ],
)
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
        "FIELD_ENCRYPTION_KEY": "fake-dev-only-field-encryption-key-0003",
        "FIELD_HASH_KEY": "fake-dev-only-field-hash-key-000000004",
    }
    check_required_settings(fake, "development")
    check_required_settings(
        {**fake, "MIGRATION_DATABASE_URL": fake["DATABASE_URL"]}, "development", "migrations"
    )


def test_development_still_needs_the_secrets_to_exist():
    assert refusal({}, "development").details["missing"] == [
        "DJANGO_SECRET_KEY",
        "DATABASE_URL",
        "FIELD_ENCRYPTION_KEY",
        "FIELD_HASH_KEY",
        "JWT_COMPANY_SECRET",
        "JWT_ADMIN_SECRET",
    ]


@pytest.mark.parametrize("value", ["fake", "Password123", "CHANGEME", "aaaa", " "])
def test_obvious_placeholders_are_recognised(value):
    assert looks_like_placeholder(value)


def test_a_random_looking_value_is_not_a_placeholder():
    assert not looks_like_placeholder("Zk3vQ8mT1xRb7LwN4pYc9HsJ2dGfA6eU")


@pytest.mark.parametrize(
    "name", ["DJANGO_SECRET_KEY", "JWT_ADMIN_SECRET", "FIELD_HASH_KEY", "DATABASE_URL"]
)
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
