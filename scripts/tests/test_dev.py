import socket

import pytest

import dev

EXAMPLE = "APP_ENV=development\nDJANGO_SECRET_KEY=fake-dev-only-secret-key\n# comment\nA=b=c\n"


def test_ensure_env_file_creates_file_with_random_secret_key(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text(EXAMPLE)
    env_file = tmp_path / ".env"

    assert dev.ensure_env_file(env_file, example) is True

    values = dev.read_env_file(env_file)
    assert values["APP_ENV"] == "development"
    assert values["DJANGO_SECRET_KEY"] != "fake-dev-only-secret-key"
    assert len(values["DJANGO_SECRET_KEY"]) >= 32


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
        "A": "b=c",
    }


def test_example_env_file_contains_only_fake_values():
    values = dev.read_env_file(dev.ENV_EXAMPLE)
    assert "fake" in values["DJANGO_SECRET_KEY"]
    assert "fake" in values["POSTGRES_PASSWORD"]
    assert values["POSTGRES_ADMIN_PASSWORD"] == ""


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
        "POSTGRES_USER": "bera",
        "POSTGRES_DB": 'bera"; DROP',
    }
    with pytest.raises(dev.SetupError, match="may only use"):
        dev.ensure_native_database(settings)


def test_unknown_command_is_reported(capsys):
    assert dev.main(["nonsense"]) == 2
    assert "Unknown command" in capsys.readouterr().out
