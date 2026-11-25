"""Staging and production must share no secret, database, bucket, port or address, and the
check must never show a value."""

import subprocess
import sys
from pathlib import Path

import pytest

from config.separation import compare

STAGING = {
    "DJANGO_SECRET_KEY": "test-only-staging-django-secret-0001",
    "JWT_COMPANY_SECRET": "test-only-staging-company-signing-01",
    "JWT_ADMIN_SECRET": "test-only-staging-admin-signing-001",
    "FIELD_ENCRYPTION_KEY": "test-only-staging-field-encryption-1",
    "FIELD_HASH_KEY": "test-only-staging-field-hash-key-01",
    "OPENAI_API_KEY": "test-only-staging-ai-key-0000000001",
    "STRIPE_SECRET_KEY": "sk_test_only_staging_0000000001",  # nosecret: fake
    "STRIPE_WEBHOOK_SECRET": "whsec_only_staging_0000000001",  # nosecret: fake
    "R2_ACCESS_KEY_ID": "test-only-staging-r2-key-id-0001",
    "R2_SECRET_ACCESS_KEY": "test-only-staging-r2-secret-0001",
    "R2_BUCKET": "bera-test-staging",
    "DATABASE_URL": "postgres://staging_app:test-only-staging-db-pw-1@127.0.0.1:5432/bera_staging",
    "MIGRATION_DATABASE_URL": "postgres://staging_mig:test-only-staging-mig-pw-1@127.0.0.1:5432/bera_staging",  # nosecret: fake
    "WEB_BASE_URL": "https://staging.example.com",
    "NEXT_PUBLIC_SITE_URL": "https://staging.example.com",
    "ALLOWED_HOSTS": "staging.example.com",
    "ALLOWED_ORIGINS": "https://staging.example.com",
    "API_PORT": "8001",
    "WEB_PORT": "3001",
}
PRODUCTION = {
    "DJANGO_SECRET_KEY": "test-only-production-django-secret-1",
    "JWT_COMPANY_SECRET": "test-only-production-company-signing1",
    "JWT_ADMIN_SECRET": "test-only-production-admin-signing-1",
    "FIELD_ENCRYPTION_KEY": "test-only-production-field-encryption1",
    "FIELD_HASH_KEY": "test-only-production-field-hash-key-1",
    "OPENAI_API_KEY": "test-only-production-ai-key-00000001",
    "STRIPE_SECRET_KEY": "sk_test_only_production_0000000001",  # nosecret: fake
    "STRIPE_WEBHOOK_SECRET": "whsec_only_production_0000000001",  # nosecret: fake
    "R2_ACCESS_KEY_ID": "test-only-production-r2-key-id-0001",
    "R2_SECRET_ACCESS_KEY": "test-only-production-r2-secret-001",
    "R2_BUCKET": "bera-test-production",
    "DATABASE_URL": "postgres://production_app:test-only-production-db-pw-1@127.0.0.1:5432/bera_production",  # nosecret: fake
    "MIGRATION_DATABASE_URL": "postgres://production_mig:test-only-production-mig-pw-1@127.0.0.1:5432/bera_production",  # nosecret: fake
    "WEB_BASE_URL": "https://www.example.com",
    "NEXT_PUBLIC_SITE_URL": "https://www.example.com",
    "ALLOWED_HOSTS": "www.example.com, example.com",
    "ALLOWED_ORIGINS": "https://www.example.com",
    "API_PORT": "8002",
    "WEB_PORT": "3002",
}


def test_two_separate_environments_pass():
    assert compare(STAGING, PRODUCTION) == []


@pytest.mark.parametrize(
    "name",
    [
        "DJANGO_SECRET_KEY",
        "JWT_COMPANY_SECRET",
        "FIELD_ENCRYPTION_KEY",
        "OPENAI_API_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "R2_SECRET_ACCESS_KEY",
    ],
)
def test_a_shared_secret_fails_and_is_named(name):
    problems = compare(STAGING, {**PRODUCTION, name: STAGING[name]})
    assert problems == [f"{name} is the same secret in both environments."]


@pytest.mark.parametrize("name", ["R2_BUCKET", "API_PORT", "WEB_PORT", "WEB_BASE_URL"])
def test_a_shared_bucket_port_or_address_fails(name):
    assert any(name in problem for problem in compare(STAGING, {**PRODUCTION, name: STAGING[name]}))


def test_a_shared_database_account_password_or_name_fails():
    same_database = {**PRODUCTION, "DATABASE_URL": STAGING["DATABASE_URL"]}
    text = " ".join(compare(STAGING, same_database))
    assert "DATABASE_URL has the same database password" in text
    assert "DATABASE_URL uses the same database account" in text
    assert "DATABASE_URL points at the same database" in text


def test_the_same_database_name_on_the_same_server_fails_even_with_other_accounts():
    url = "postgres://production_app:test-only-production-db-pw-1@127.0.0.1:5432/bera_staging"  # nosecret: fake
    assert any(
        "points at the same database" in problem
        for problem in compare(STAGING, {**PRODUCTION, "DATABASE_URL": url})
    )


@pytest.mark.parametrize("name", ["ALLOWED_HOSTS", "ALLOWED_ORIGINS"])
def test_one_shared_address_in_a_list_fails(name):
    other = {**PRODUCTION, name: f"{PRODUCTION[name]}, {STAGING[name]}/"}
    assert compare(STAGING, other) == [f"{name} shares an address with the other environment."]


def test_a_missing_setting_is_reported_not_ignored():
    problems = compare({**STAGING, "API_PORT": ""}, PRODUCTION)
    assert "API_PORT is missing in staging." in problems


def test_no_message_ever_holds_a_value():
    problems = compare(STAGING, {**STAGING})
    assert problems
    everything = " ".join(problems)
    for value in STAGING.values():
        if len(value) > 6:
            assert value not in everything


def write(path, values):
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")


def run_check(tmp_path, staging, production):
    write(tmp_path / "staging.env", staging)
    write(tmp_path / "production.env", production)
    script = Path(__file__).resolve().parents[3] / "scripts" / "check_environments.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            str(tmp_path / "staging.env"),
            str(tmp_path / "production.env"),
        ],
        capture_output=True,
        text=True,
    )


def test_the_command_passes_for_separate_files(tmp_path):
    result = run_check(tmp_path, STAGING, PRODUCTION)
    assert result.returncode == 0
    assert "separate" in result.stdout


def test_the_command_fails_and_prints_names_never_values(tmp_path):
    shared = {**PRODUCTION, "STRIPE_WEBHOOK_SECRET": STAGING["STRIPE_WEBHOOK_SECRET"]}
    result = run_check(tmp_path, STAGING, shared)
    assert result.returncode == 1
    assert "STRIPE_WEBHOOK_SECRET" in result.stdout
    assert STAGING["STRIPE_WEBHOOK_SECRET"] not in result.stdout + result.stderr
