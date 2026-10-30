"""Runs against real accounts in the test database: the proof that the app account is limited."""

import secrets

import psycopg
import pytest
from django.core.management import call_command
from django.db import connection

from core.database_roles import Account, Accounts, _password_verifier, problems_with_app_account
from core.errors import ConfigurationError

TABLE = "protection_probe"
ROLES = ("app", "backup", "stranger")

pytestmark = pytest.mark.django_db(transaction=True)


def connect(user, password, **extra):
    settings_dict = connection.settings_dict
    return psycopg.connect(
        host=settings_dict["HOST"] or "127.0.0.1",
        port=settings_dict["PORT"] or 5432,
        dbname=settings_dict["NAME"],
        user=user,
        password=password,
        autocommit=True,
        **extra,
    )


def address(user, password):
    settings_dict = connection.settings_dict
    host = settings_dict["HOST"] or "127.0.0.1"
    port = settings_dict["PORT"] or 5432
    name = settings_dict["NAME"]
    return f"postgres://{user}:{password}@{host}:{port}/{name}"  # nosecret: built at run time


@pytest.fixture
def accounts(monkeypatch):
    """Fresh, uniquely named accounts; the migrator is the account running the tests."""
    suffix = secrets.token_hex(4)
    made = {role: (f"test_only_{role}_{suffix}", secrets.token_hex(12)) for role in ROLES}
    current = (connection.settings_dict["USER"], connection.settings_dict["PASSWORD"])
    monkeypatch.setenv("ADMIN_DATABASE_URL", address(*current))
    monkeypatch.setenv("MIGRATION_DATABASE_URL", address(*current))
    monkeypatch.setenv("DATABASE_URL", address(*made["app"]))
    monkeypatch.setenv("BACKUP_DATABASE_URL", address(*made["backup"]))
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE {TABLE} (id serial PRIMARY KEY, note text)")
        cursor.execute(f"INSERT INTO {TABLE} (note) VALUES ('before the accounts existed')")
    yield made
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {TABLE}, {TABLE}_later")
        for name, _ in made.values():
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [name])
            if not cursor.fetchone():
                continue
            # The account that created a role may manage it, but must first take up its rights.
            cursor.execute(f'GRANT "{name}" TO CURRENT_USER WITH INHERIT TRUE, SET TRUE')
            cursor.execute(f'DROP OWNED BY "{name}"')
            cursor.execute(f'DROP ROLE IF EXISTS "{name}"')


@pytest.fixture
def provisioned(accounts):
    with connection.cursor() as cursor:
        name, password = accounts["stranger"]
        cursor.execute(f"CREATE ROLE \"{name}\" LOGIN PASSWORD '{password}'")
    call_command("provision_database_roles")
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE {TABLE}_later (id serial PRIMARY KEY, note text)")
    return accounts


class TestAppAccountRights:
    @pytest.mark.parametrize("table", [TABLE, f"{TABLE}_later"])
    def test_it_reads_and_writes_rows_in_old_and_new_tables(self, provisioned, table):
        with connect(*provisioned["app"]) as app, app.cursor() as cursor:
            cursor.execute(f"INSERT INTO {table} (note) VALUES ('written by the app')")
            cursor.execute(f"UPDATE {table} SET note = 'changed' WHERE note = 'written by the app'")
            cursor.execute(f"SELECT count(*) FROM {table}")
            cursor.execute(f"DELETE FROM {table} WHERE note = 'changed'")
            cursor.execute("SELECT nextval(pg_get_serial_sequence(%s, 'id'))", [table])

    @pytest.mark.parametrize(
        "statement",
        [
            "CREATE TABLE made_by_the_app (id int)",
            f"ALTER TABLE {TABLE} ADD COLUMN extra text",
            f"ALTER TABLE {TABLE} DROP COLUMN note",
            f"ALTER TABLE {TABLE}_later RENAME TO renamed",
            f"DROP TABLE {TABLE}",
            f"DROP TABLE {TABLE}_later",
            f"TRUNCATE {TABLE}",
            f"CREATE INDEX made_by_the_app ON {TABLE} (note)",
            f"CREATE VIEW made_by_the_app AS SELECT * FROM {TABLE}",
            "CREATE SCHEMA made_by_the_app",
            "DROP SCHEMA public CASCADE",
            "CREATE ROLE made_by_the_app LOGIN",
            "CREATE DATABASE made_by_the_app",
            "SELECT * FROM pg_shadow",
        ],
    )
    def test_it_cannot_change_the_structure_or_the_accounts(self, provisioned, statement):
        with connect(*provisioned["app"]) as app, app.cursor() as cursor:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(statement)

    def test_the_structure_is_unchanged_after_all_that(self, provisioned):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = %s ORDER BY 1",
                [TABLE],
            )
            assert [row[0] for row in cursor.fetchall()] == ["id", "note"]

    def test_it_holds_no_special_rights(self, provisioned):
        with connect(*provisioned["app"]) as app, app.cursor() as cursor:
            assert problems_with_app_account(cursor, require_encryption=False) == []


class TestBackupAccountRights:
    def test_it_reads_old_and_new_tables(self, provisioned):
        with connect(*provisioned["backup"]) as backup, backup.cursor() as cursor:
            for table in (TABLE, f"{TABLE}_later"):
                cursor.execute(f"SELECT count(*) FROM {table}")

    @pytest.mark.parametrize(
        "statement",
        [
            f"INSERT INTO {TABLE} (note) VALUES ('x')",
            f"UPDATE {TABLE} SET note = 'x'",
            f"DELETE FROM {TABLE}",
            f"TRUNCATE {TABLE}",
            "CREATE TABLE made_by_the_backup (id int)",
        ],
    )
    def test_it_cannot_write_or_change_anything(self, provisioned, statement):
        with connect(*provisioned["backup"]) as backup, backup.cursor() as cursor:
            with pytest.raises(psycopg.Error):
                cursor.execute(statement)

    def test_the_rights_alone_refuse_a_write_even_if_read_only_is_switched_off(self, provisioned):
        with connect(*provisioned["backup"]) as backup, backup.cursor() as cursor:
            cursor.execute("SET default_transaction_read_only = off")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(f"INSERT INTO {TABLE} (note) VALUES ('x')")


class TestOtherAccounts:
    def test_an_account_that_was_not_named_cannot_even_connect(self, provisioned):
        with pytest.raises(psycopg.OperationalError):
            connect(*provisioned["stranger"])

    def test_the_account_running_the_tests_still_changes_the_structure(self, provisioned):
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {TABLE} ADD COLUMN extra text")


class TestProvisioning:
    def test_it_can_be_repeated(self, provisioned):
        call_command("provision_database_roles")
        with connect(*provisioned["app"]) as app, app.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {TABLE}")

    def test_the_password_is_hashed_before_it_is_sent_to_the_server(self, accounts):
        password = accounts["app"][1]
        with connect(*self.current()) as admin:
            verifier = _password_verifier(admin, Account(accounts["app"][0], password))
            text = verifier.as_string(admin)
        assert "SCRAM-SHA-256$" in text and password not in text

    @staticmethod
    def current():
        return connection.settings_dict["USER"], connection.settings_dict["PASSWORD"]

    def test_it_refuses_two_roles_sharing_one_account(self, accounts, monkeypatch):
        monkeypatch.setenv("BACKUP_DATABASE_URL", address(*accounts["app"]))
        with pytest.raises(ConfigurationError) as caught:
            call_command("provision_database_roles")
        assert "three different accounts" in caught.value.message

    @pytest.mark.parametrize("name", ["ADMIN_DATABASE_URL", "BACKUP_DATABASE_URL"])
    def test_it_says_which_address_is_missing(self, accounts, monkeypatch, name):
        monkeypatch.setenv(name, "")
        with pytest.raises(ConfigurationError) as caught:
            call_command("provision_database_roles")
        assert caught.value.details == {"missing": [name]}

    def test_an_address_without_a_password_is_refused(self):
        with pytest.raises(ConfigurationError):
            Account.from_url("DATABASE_URL", "postgres://someone@127.0.0.1/bera")

    def test_staging_and_production_refuse_placeholder_passwords_before_connecting(
        self, accounts, monkeypatch, settings
    ):
        settings.APP_ENV = "production"
        monkeypatch.setenv("DATABASE_URL", address(accounts["app"][0], "changeme"))
        with pytest.raises(ConfigurationError) as caught:
            call_command("provision_database_roles")
        assert "changeme" not in caught.value.message + str(caught.value.details)

    def test_the_accounts_must_have_three_different_names(self):
        same = Account("one_account", "a-password-value")
        with pytest.raises(ConfigurationError):
            Accounts(app=same, migrator=Account("another", "x" * 12), backup=same)


class FakeCursor:
    """Answers the three questions `problems_with_app_account` asks."""

    def __init__(self, flags, can_create, encrypted):
        self.answers = [flags, can_create, (encrypted,)]
        self.current = None

    def execute(self, query, params=None):
        self.current = self.answers.pop(0)

    def fetchone(self):
        return self.current


class TestCheckingTheConnection:
    SAFE = (False, False, False, False, False)

    def test_a_limited_encrypted_account_has_no_problems(self):
        cursor = FakeCursor(self.SAFE, (False, False), True)
        assert problems_with_app_account(cursor, require_encryption=True) == []

    def test_an_unencrypted_connection_is_a_problem_when_encryption_is_required(self):
        cursor = FakeCursor(self.SAFE, (False, False), False)
        assert problems_with_app_account(cursor, require_encryption=True) == [
            "the connection is not encrypted"
        ]

    def test_an_unencrypted_connection_is_fine_when_encryption_is_not_required(self):
        cursor = FakeCursor(self.SAFE, (False, False), False)
        # Only two answers are used: the encryption question is never asked.
        assert problems_with_app_account(cursor, require_encryption=False) == []

    def test_every_extra_right_is_named(self):
        cursor = FakeCursor((True, True, True, True, True), (True, True), True)
        problems = problems_with_app_account(cursor, require_encryption=True)
        assert len(problems) == 7

    def test_the_account_running_the_tests_is_reported_as_too_powerful(self):
        with connection.cursor() as cursor:
            assert problems_with_app_account(cursor, require_encryption=False) != []
        with pytest.raises(ConfigurationError) as caught:
            call_command("check_database_protection")
        assert "problems" in caught.value.details

    def test_a_connection_with_encryption_switched_off_is_reported(self, provisioned):
        with connect(*provisioned["app"], sslmode="disable") as app, app.cursor() as cursor:
            assert problems_with_app_account(cursor, require_encryption=True) == [
                "the connection is not encrypted"
            ]
