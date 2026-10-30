"""Starts a fresh Python process, because settings are read once at start-up."""

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
}


def load_settings(app_env, **overrides):
    environ = {key: value for key, value in os.environ.items() if key not in FAKE_VALUES}
    environ.update({"APP_ENV": app_env, "PYTHONPATH": str(SERVER_DIR), **FAKE_VALUES, **overrides})
    script = (
        "import json, config.settings as s;"
        "print(json.dumps({'debug': s.DEBUG, 'hosts': s.ALLOWED_HOSTS}))"
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
        "JWT_COMPANY_SECRET",
        "JWT_ADMIN_SECRET",
    ],
)
def test_production_refuses_to_start_when_a_required_secret_is_missing(missing):
    result = load_settings("production", **{missing: ""})
    assert result.returncode != 0
    assert missing in result.stderr
    assert "fake-test-secret-key" not in result.stderr
