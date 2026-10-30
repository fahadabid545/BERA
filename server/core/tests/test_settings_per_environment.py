"""Starts a fresh Python process, because settings are read once at start-up."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]
FAKE_VALUES = {
    "DJANGO_SECRET_KEY": "test-only-django-secret-key-0000-1111-2222",
    "JWT_COMPANY_SECRET": "test-only-company-signing-key-3a9f1c7e5b",
    "JWT_ADMIN_SECRET": "test-only-admin-signing-key-8d2e6b4f0a",
    "DATABASE_URL": "postgres://app:test-only-db-pw-3141592653@127.0.0.1:5432/bera?sslmode=verify-full",
    "MIGRATION_DATABASE_URL": "postgres://migrator:test-only-migrator-pw-2718281828@127.0.0.1:5432/bera?sslmode=verify-full",  # nosecret: fake
    "FIELD_ENCRYPTION_KEY": "test-only-field-encryption-key-7c1d9e",
    "FIELD_HASH_KEY": "test-only-field-hash-key-4b8a2f6d03",
    "ALLOWED_HOSTS": "staging.example.com, www.example.com",
    "TRUSTED_PROXY_COUNT": "1",
    "ALLOWED_ORIGINS": "https://staging.example.com, https://www.example.com/",
}


def load_settings(app_env, **overrides):
    # The test run itself uses the migrator account; a started app does not.
    ignored = {*FAKE_VALUES, "DATABASE_ROLE"}
    environ = {key: value for key, value in os.environ.items() if key not in ignored}
    environ.update({"APP_ENV": app_env, "PYTHONPATH": str(SERVER_DIR), **FAKE_VALUES, **overrides})
    script = (
        "import json, config.settings as s;"
        "print(json.dumps({'debug': s.DEBUG, 'hosts': s.ALLOWED_HOSTS,"
        " 'origins': s.ALLOWED_ORIGINS, 'hsts': getattr(s, 'SECURE_HSTS_SECONDS', 0),"
        " 'redirect': getattr(s, 'SECURE_SSL_REDIRECT', False),"
        " 'referrer': s.SECURE_REFERRER_POLICY, 'proxies': s.TRUSTED_PROXY_COUNT,"
        " 'db_user': s.DATABASES['default']['USER']}))"
    )
    return subprocess.run(
        [sys.executable, "-c", script], env=environ, capture_output=True, text=True, cwd="/"
    )


def test_development_allows_debug_and_local_hosts():
    result = load_settings("development")
    assert result.returncode == 0, result.stderr
    assert '"debug": true' in result.stdout and "localhost" in result.stdout


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_and_production_turn_debug_off_and_read_hosts(app_env):
    result = load_settings(app_env)
    assert result.returncode == 0, result.stderr
    assert '"debug": false' in result.stdout
    assert '"hosts": ["staging.example.com", "www.example.com"]' in result.stdout


@pytest.mark.parametrize(
    "missing",
    [
        "DJANGO_SECRET_KEY",
        "DATABASE_URL",
        "ALLOWED_HOSTS",
        "ALLOWED_ORIGINS",
        "TRUSTED_PROXY_COUNT",
        "JWT_COMPANY_SECRET",
        "JWT_ADMIN_SECRET",
        "FIELD_ENCRYPTION_KEY",
        "FIELD_HASH_KEY",
    ],
)
def test_production_refuses_to_start_when_a_required_secret_is_missing(missing):
    result = load_settings("production", **{missing: ""})
    assert result.returncode != 0
    assert missing in result.stderr
    assert "test-only-django-secret-key-0000-1111-2222" not in result.stderr


def settings_of(app_env, **overrides):
    result = load_settings(app_env, **overrides)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_development_allows_only_the_local_web_app_and_skips_https_rules():
    values = settings_of("development")
    assert values["origins"] == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert values["hsts"] == 0 and values["redirect"] is False
    assert values["referrer"] == "no-referrer"


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_and_production_allow_only_their_https_addresses_and_force_https(app_env):
    values = settings_of(app_env)
    assert values["origins"] == ["https://staging.example.com", "https://www.example.com"]
    assert values["hsts"] == 31_536_000 and values["redirect"] is True


@pytest.mark.parametrize("bad", ["http://staging.example.com", "staging.example.com", "*", " , "])
def test_production_refuses_origins_that_are_not_https_addresses(bad):
    result = load_settings("production", ALLOWED_ORIGINS=bad)
    assert result.returncode != 0
    assert "ALLOWED_ORIGINS" in result.stderr


def test_development_has_no_proxy_in_front_of_the_server():
    assert settings_of("development")["proxies"] == 0


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_and_production_read_the_number_of_proxies(app_env):
    assert settings_of(app_env)["proxies"] == 1


@pytest.mark.parametrize("bad", ["many", "-1", "99", "1.5", "0x1"])
def test_production_refuses_a_proxy_count_that_is_not_a_small_whole_number(bad):
    result = load_settings("production", TRUSTED_PROXY_COUNT=bad)
    assert result.returncode != 0
    assert "TRUSTED_PROXY_COUNT" in result.stderr


@pytest.mark.parametrize("app_env", ["development", "staging", "production"])
def test_the_app_connects_with_the_app_account(app_env):
    assert settings_of(app_env)["db_user"] == "app"


@pytest.mark.parametrize("app_env", ["development", "staging", "production"])
def test_structure_changes_connect_with_the_migrator_account(app_env):
    assert settings_of(app_env, DATABASE_ROLE="migrations")["db_user"] == "migrator"


def test_an_unknown_database_role_is_refused():
    result = load_settings("development", DATABASE_ROLE="superuser")
    assert result.returncode != 0 and "DATABASE_ROLE" in result.stderr


@pytest.mark.parametrize("app_env", ["staging", "production"])
@pytest.mark.parametrize(
    "ending", ["", "?sslmode=disable", "?sslmode=allow", "?sslmode=prefer", "?connect_timeout=5"]
)
@pytest.mark.parametrize(
    ("role", "setting"),
    [("app", "DATABASE_URL"), ("migrations", "MIGRATION_DATABASE_URL")],
)
def test_staging_and_production_refuse_a_connection_that_may_be_unencrypted(
    app_env, ending, role, setting
):
    address = FAKE_VALUES[setting].split("?")[0] + ending
    result = load_settings(app_env, DATABASE_ROLE=role, **{setting: address})
    assert result.returncode != 0
    assert setting in result.stderr and "sslmode" in result.stderr


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_production_accepts_every_encrypted_mode(mode):
    address = FAKE_VALUES["DATABASE_URL"].split("?")[0] + f"?sslmode={mode}"
    assert load_settings("production", DATABASE_URL=address).returncode == 0


def test_development_may_connect_without_encryption():
    address = FAKE_VALUES["DATABASE_URL"].split("?")[0]
    assert load_settings("development", DATABASE_URL=address).returncode == 0


@pytest.mark.parametrize("key", ["FIELD_ENCRYPTION_KEY", "FIELD_HASH_KEY"])
def test_the_field_keys_must_be_long_enough(key):
    result = load_settings("development", **{key: "too-short"})
    assert result.returncode != 0 and key in result.stderr


def test_the_two_field_keys_must_differ():
    result = load_settings("development", FIELD_HASH_KEY=FAKE_VALUES["FIELD_ENCRYPTION_KEY"])
    assert result.returncode != 0 and "must be different" in result.stderr
