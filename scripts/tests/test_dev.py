import socket

import pytest

import dev

EXAMPLE = (
    "APP_ENV=development\nDJANGO_SECRET_KEY=fake-dev-only-secret-key\n"
    "JWT_COMPANY_SECRET=fake-company\nJWT_ADMIN_SECRET=fake-admin\n# comment\nA=b=c\n"
)


def test_ensure_env_file_creates_file_with_random_secret_key(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text(EXAMPLE)
    env_file = tmp_path / ".env"

    assert dev.ensure_env_file(env_file, example) is True

    values = dev.read_env_file(env_file)
    assert values["APP_ENV"] == "development"
    assert values["DJANGO_SECRET_KEY"] != "fake-dev-only-secret-key"
    assert len(values["DJANGO_SECRET_KEY"]) >= 32
    signing = {values["JWT_COMPANY_SECRET"], values["JWT_ADMIN_SECRET"]}
    assert len(signing) == 2 and all(len(secret) >= 32 for secret in signing)


def test_ensure_env_file_never_overwrites_existing_file(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text(EXAMPLE)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=staging\n")

    assert dev.ensure_env_file(env_file, example) is False
    assert env_file.read_text() == "APP_ENV=staging\n"


def test_read_env_file_ignores_comments_and_keeps_equals_in_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(EXAMPLE)

    assert dev.read_env_file(env_file) == {
        "APP_ENV": "development",
        "DJANGO_SECRET_KEY": "fake-dev-only-secret-key",
        "JWT_COMPANY_SECRET": "fake-company",
        "JWT_ADMIN_SECRET": "fake-admin",
        "A": "b=c",
    }


def test_example_env_file_contains_only_fake_values():
    values = dev.read_env_file(dev.ENV_EXAMPLE)
    assert "fake" in values["DJANGO_SECRET_KEY"]
    for name in (
        "POSTGRES_ADMIN_PASSWORD",
        "FIELD_ENCRYPTION_KEY",
        "FIELD_HASH_KEY",
        "DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "BACKUP_DATABASE_URL",
    ):
        assert "fake" in values[name]


def test_the_example_gives_each_database_account_its_own_name_and_password():
    values = dev.read_env_file(dev.ENV_EXAMPLE)
    addresses = [
        values[name] for name in ("DATABASE_URL", "MIGRATION_DATABASE_URL", "BACKUP_DATABASE_URL")
    ]
    logins = {address.split("://")[1].split("@")[0] for address in addresses}
    assert len(logins) == 3


def test_a_new_env_file_gets_random_field_keys(tmp_path):
    env_file = tmp_path / ".env"
    dev.ensure_env_file(env_file, dev.ENV_EXAMPLE)
    values = dev.read_env_file(env_file)
    assert "fake" not in values["FIELD_ENCRYPTION_KEY"] + values["FIELD_HASH_KEY"]
    assert values["FIELD_ENCRYPTION_KEY"] != values["FIELD_HASH_KEY"]


def test_the_administrator_address_is_escaped_and_points_at_this_computer():
    address = dev.admin_database_url(
        {
            "POSTGRES_ADMIN_USER": "postgres",
            "POSTGRES_ADMIN_PASSWORD": "p@ss/word",  # nosecret: fake
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "bera",
        }
    )
    assert address == "postgres://postgres:p%40ss%2Fword@127.0.0.1:5432/bera"  # nosecret: fake


def test_port_in_use_detects_a_listening_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert dev.port_in_use(port) is True
    assert dev.port_in_use(port) is False


def test_require_free_port_explains_what_to_do():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(dev.SetupError, match="already in use"):
            dev.require_free_port(port, "API")


def test_sql_literal_escapes_quotes():
    assert dev.sql_literal("it's") == "'it''s'"


def test_native_setup_without_psql_prints_install_steps(monkeypatch):
    monkeypatch.setattr(dev.shutil, "which", lambda name: None)
    with pytest.raises(dev.SetupError, match="Install Docker Desktop"):
        dev.ensure_native_database({})


def test_native_setup_rejects_unsafe_database_names(monkeypatch):
    monkeypatch.setattr(dev.shutil, "which", lambda name: "psql")
    settings = {
        "POSTGRES_ADMIN_PASSWORD": "x",
        "POSTGRES_DB": 'bera"; DROP',
    }
    with pytest.raises(dev.SetupError, match="may only use"):
        dev.ensure_native_database(settings)


def test_unknown_command_is_reported(capsys):
    assert dev.main(["nonsense"]) == 2
    assert "Unknown command" in capsys.readouterr().out
