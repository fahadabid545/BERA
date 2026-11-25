import datetime
import os
import types

import origin_pull_certificate as certificates
import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID
from harden_common import HardeningError


def create(tmp_path, env, **changes):
    arguments = types.SimpleNamespace(env=env, out=tmp_path, dry_run=False, **changes)
    certificates.create(arguments)


def load(tmp_path, name):
    return x509.load_pem_x509_certificate((tmp_path / name).read_bytes())


@pytest.fixture(scope="module")
def pairs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("pairs")
    for env in certificates.ENVIRONMENTS:
        create(folder, env)
    return folder


def test_three_files_are_made_and_only_the_key_is_private(pairs):
    names = sorted(path.name for path in pairs.iterdir() if path.name.startswith("production"))
    assert names == [
        "production-client.key",
        "production-client.pem",
        "production-origin-pull-ca.pem",
    ]
    assert oct(os.stat(pairs / "production-client.key").st_mode & 0o777) == "0o600"


def test_the_client_certificate_is_signed_by_our_authority_for_client_use(pairs):
    client, authority = (
        load(pairs, "production-client.pem"),
        load(pairs, "production-origin-pull-ca.pem"),
    )
    client.verify_directly_issued_by(authority)
    usage = client.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert list(usage) == [ExtendedKeyUsageOID.CLIENT_AUTH]
    basic = client.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert basic.ca is False


def test_the_authority_can_only_sign_clients_and_nothing_below_them(pairs):
    basic = (
        load(pairs, "production-origin-pull-ca.pem")
        .extensions.get_extension_for_class(x509.BasicConstraints)
        .value
    )
    assert basic.ca is True and basic.path_length == 0


def test_staging_and_production_do_not_trust_each_other(pairs):
    staging_client = load(pairs, "staging-client.pem")
    production_authority = load(pairs, "production-origin-pull-ca.pem")
    with pytest.raises(Exception):  # noqa: B017 - the library names several errors for "no"
        staging_client.verify_directly_issued_by(production_authority)
    production_client = load(pairs, "production-client.pem")
    with pytest.raises(Exception):  # noqa: B017
        production_client.verify_directly_issued_by(load(pairs, "staging-origin-pull-ca.pem"))


def test_the_authority_private_key_is_never_saved(pairs):
    for path in pairs.iterdir():
        assert b"PRIVATE KEY" not in path.read_bytes() or path.name.endswith("-client.key")
    key_text = (pairs / "production-client.key").read_bytes()
    assert key_text.count(b"PRIVATE KEY") == 2  # begin and end of the one client key


def test_each_run_makes_new_keys(tmp_path):
    create(tmp_path / "a", "staging")
    create(tmp_path / "b", "staging")
    assert (tmp_path / "a" / "staging-client.key").read_bytes() != (
        tmp_path / "b" / "staging-client.key"
    ).read_bytes()


def test_nothing_is_overwritten(tmp_path):
    create(tmp_path, "staging")
    before = (tmp_path / "staging-client.key").read_bytes()
    with pytest.raises(HardeningError, match="already exists"):
        create(tmp_path, "staging")
    assert (tmp_path / "staging-client.key").read_bytes() == before


def test_a_dry_run_creates_nothing(tmp_path, capsys):
    certificates.create(types.SimpleNamespace(env="staging", out=tmp_path / "x", dry_run=True))
    assert not (tmp_path / "x").exists()
    assert "staging-client.key" in capsys.readouterr().out


def test_the_check_reports_days_left_and_warns_when_close(pairs, monkeypatch, capsys):
    arguments = types.SimpleNamespace(folder=pairs)
    assert certificates.check(arguments) == 0
    assert "days left" in capsys.readouterr().out
    monkeypatch.setattr(certificates, "WARN_DAYS", 10_000)
    assert certificates.check(arguments) == 1
    assert "RENEW SOON" in capsys.readouterr().out


def test_the_check_fails_for_missing_files(tmp_path):
    assert certificates.check(types.SimpleNamespace(folder=tmp_path)) == 1


def test_the_validity_is_about_two_years(pairs):
    client = load(pairs, "production-client.pem")
    length = client.not_valid_after_utc - client.not_valid_before_utc
    assert datetime.timedelta(days=700) < length < datetime.timedelta(days=760)
