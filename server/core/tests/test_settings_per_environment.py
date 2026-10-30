"""Starts a fresh Python process, because settings are read once at start-up."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]
FAKE_VALUES = {
    "DJANGO_SECRET_KEY": "fake-test-secret-key",
    "JWT_COMPANY_SECRET": "fake-test-company-signing-secret-000001",
    "JWT_ADMIN_SECRET": "fake-test-admin-signing-secret-0000002",
    "DATABASE_URL": "postgres://user:fake-password@127.0.0.1:5432/fake",
    "ALLOWED_HOSTS": "staging.example.com, www.example.com",
    "TRUSTED_PROXY_COUNT": "1",
    "ALLOWED_ORIGINS": "https://staging.example.com, https://www.example.com/",
}


def load_settings(app_env, **overrides):
    environ = {key: value for key, value in os.environ.items() if key not in FAKE_VALUES}
    environ.update({"APP_ENV": app_env, "PYTHONPATH": str(SERVER_DIR), **FAKE_VALUES, **overrides})
    script = (
        "import json, config.settings as s;"
        "print(json.dumps({'debug': s.DEBUG, 'hosts': s.ALLOWED_HOSTS,"
        " 'origins': s.ALLOWED_ORIGINS, 'hsts': getattr(s, 'SECURE_HSTS_SECONDS', 0),"
        " 'redirect': getattr(s, 'SECURE_SSL_REDIRECT', False),"
        " 'referrer': s.SECURE_REFERRER_POLICY, 'proxies': s.TRUSTED_PROXY_COUNT}))"
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
    ],
)
def test_production_refuses_to_start_when_a_required_secret_is_missing(missing):
    result = load_settings("production", **{missing: ""})
    assert result.returncode != 0
    assert missing in result.stderr
    assert "fake-test-secret-key" not in result.stderr


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
