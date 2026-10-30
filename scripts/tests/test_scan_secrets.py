"""The sample secrets are built from pieces so this file never contains one itself."""

import subprocess
import sys

import pytest

import scan_secrets

SAMPLES = {
    "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "OpenAI-style key": 'client = Client("sk-' + "proj" + "Ab3dE6gH9jK2mN5pQ8sT1vX4zC7" + '")',
    "Stripe key": "key = 'sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc'",
    "Stripe webhook secret": "whsec_" + "Ab3dE6gH9jK2mN5pQ8sT1vX4",
    "AWS access key": "AKIA" + "IOSFODNN7ABCDEFG",
    "GitHub token": "ghp_" + "Ab3dE6gH9jK2mN5pQ8sT1vX4zC7bF0hJ3kL",
    "Slack token": "xoxb-" + "123456789012-abcdefghijkl",
    "signed token": "eyJ"
    + "hbGciOiJIUzI1NiJ9"
    + "."
    + "eyJzdWIiOiIxMjM0NTY3ODkw"
    + "."
    + "SflKxwRJSMeKKF2QT4fw",
    "database address with password": "postgres://app:" + "Zk3vQ8mT1xRb7LwN@db.internal/bera",
    "secret-looking value assigned to a secret-like name": 'api_key = "'
    + "Zk3vQ8mT1xRb7LwN4pYc9HsJ2dGf"
    + '"',
}


@pytest.mark.parametrize(("kind", "line"), SAMPLES.items(), ids=SAMPLES)
def test_each_kind_of_secret_is_found(kind, line):
    assert [found for _, found in scan_secrets.scan_text(line)] == [kind]


@pytest.mark.parametrize(
    "line",
    [
        "DJANGO_SECRET_KEY=fake-dev-only-secret-key",
        'password = "test-only-db-pw-3141592653"',
        "DATABASE_URL=postgres://bera:fake-dev-db-password@127.0.0.1:5432/bera",
        'token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaa"',  # not random
        'secret = "short"',
        "sk_live_ is a prefix",
        'api_key = os.environ["API_KEY"]',
        SAMPLES["OpenAI-style key"] + "  # nosecret: documentation sample",
    ],
)
def test_ordinary_and_fake_lines_are_not_flagged(line):
    assert scan_secrets.scan_text(line) == []


def test_the_scanner_reports_where_but_never_prints_the_secret(tmp_path, capsys):
    leaked = tmp_path / "settings.py"
    leaked.write_text("x = 1\n" + SAMPLES["Stripe key"] + "\n", encoding="utf-8")
    assert scan_secrets.main([str(leaked)]) == 1
    output = capsys.readouterr().out
    assert "settings.py:2: looks like a Stripe key" in output
    assert "4eC39Hq" not in output


def test_a_tracked_env_file_is_a_finding(tmp_path):
    env_file = tmp_path / ".env.production"
    env_file.write_text("A=b\n", encoding="utf-8")
    assert scan_secrets.misplaced_env_files([env_file, tmp_path / ".env.example"]) == [env_file]


def test_the_whole_project_is_clean():
    result = subprocess.run(
        [sys.executable, str(scan_secrets.ROOT / "scripts" / "scan_secrets.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout
