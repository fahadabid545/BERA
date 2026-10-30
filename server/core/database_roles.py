"""The three database accounts and the rights each one has.

    app       what the website and workers connect with: read and write rows, nothing else.
              It cannot create, change or drop tables, nor create accounts.
    migrator  owns the tables and changes the structure. Used only while deploying
              (`migrate`), never by the running app.
    backup    reads everything and can write nothing.

`provision_accounts` is safe to repeat: it creates what is missing and sets the rights to
exactly this list. It runs with an administrator account that is never used by the app.
"""

from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from psycopg import sql

from .errors import ConfigurationError

PASSWORD_HASH = b"scram-sha-256"
# Names the rights, so a failed check says what is wrong without exposing the database.
PROBLEMS = {
    "rolsuper": "is a superuser",
    "rolcreatedb": "can create databases",
    "rolcreaterole": "can create accounts",
    "rolreplication": "can copy the whole database",
    "rolbypassrls": "ignores row security",
}


@dataclass(frozen=True)
class Account:
    name: str
    password: str

    @classmethod
    def from_url(cls, setting_name, url):
        parts = urlsplit(url)
        if not parts.username or not parts.password:
            raise ConfigurationError(
                f"{setting_name} must contain the account name and password.",
                {"missing": [setting_name]},
            )
        return cls(unquote(parts.username), unquote(parts.password))


@dataclass(frozen=True)
class Accounts:
    app: Account
    migrator: Account
    backup: Account

    def __post_init__(self):
        names = [self.app.name, self.migrator.name, self.backup.name]
        if len(set(names)) < len(names):
            raise ConfigurationError(
                "The app, migrator and backup accounts must be three different accounts.",
                {"must_differ": ["DATABASE_URL", "MIGRATION_DATABASE_URL", "BACKUP_DATABASE_URL"]},
            )


def _role_exists(cursor, name):
    cursor.execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = {}").format(sql.Literal(name)))
    return cursor.fetchone() is not None


def _password_verifier(connection, account):
    """Hashed here, so the server's statement log never holds the password."""
    hashed = connection.pgconn.encrypt_password(
        account.password.encode(), account.name.encode(), PASSWORD_HASH
    )
    return sql.Literal(hashed.decode())


def _prepare_account(connection, account, *, limited, development):
    """Create the account, or reset its password. The app and backup accounts are narrowed
    again each time. The migrator is not (a role cannot narrow itself), and the rights only a
    superuser may change are set when an account is created; `problems_with_app_account`
    reports an account that has them anyway."""
    name = sql.Identifier(account.name)
    password = _password_verifier(connection, account)
    extra = sql.SQL("NOCREATEDB NOCREATEROLE")
    if development and not limited:
        # Lets the test run create its throwaway database and accounts. Never in staging
        # or production.
        extra = sql.SQL("CREATEDB CREATEROLE")
    with connection.cursor() as cursor:
        if not _role_exists(cursor, account.name):
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOREPLICATION NOBYPASSRLS {}"
                ).format(name, password, extra)
            )
        elif limited:
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {} {}").format(name, password, extra)
            )
        else:
            cursor.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(name, password))


def provision_accounts(connection, accounts, database_name, *, development=False):
    """`connection` is an administrator's, with autocommit on."""
    database = sql.Identifier(database_name)
    migrator, app, backup = (
        sql.Identifier(accounts.migrator.name),
        sql.Identifier(accounts.app.name),
        sql.Identifier(accounts.backup.name),
    )
    _prepare_account(connection, accounts.migrator, limited=False, development=development)
    _prepare_account(connection, accounts.app, limited=True, development=False)
    _prepare_account(connection, accounts.backup, limited=True, development=False)

    statements = [
        "ALTER DATABASE {database} OWNER TO {migrator}",
        "ALTER SCHEMA public OWNER TO {migrator}",
        # Nobody gets in or creates anything unless it is named below.
        "REVOKE ALL ON DATABASE {database} FROM PUBLIC",
        "REVOKE ALL ON SCHEMA public FROM PUBLIC",
        "GRANT CONNECT ON DATABASE {database} TO {app}, {backup}",
        "GRANT USAGE ON SCHEMA public TO {app}, {backup}",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app}",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {app}",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO {backup}",
        "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {backup}",
        # Tables the migrator creates later get the same rights without another step.
        "ALTER DEFAULT PRIVILEGES FOR ROLE {migrator} IN SCHEMA public"
        " GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app}",
        "ALTER DEFAULT PRIVILEGES FOR ROLE {migrator} IN SCHEMA public"
        " GRANT USAGE, SELECT ON SEQUENCES TO {app}",
        "ALTER DEFAULT PRIVILEGES FOR ROLE {migrator} IN SCHEMA public"
        " GRANT SELECT ON TABLES TO {backup}",
        "ALTER DEFAULT PRIVILEGES FOR ROLE {migrator} IN SCHEMA public"
        " GRANT SELECT ON SEQUENCES TO {backup}",
        # A second lock: even a write the backup account tries is refused.
        "ALTER ROLE {backup} SET default_transaction_read_only = on",
    ]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(
                sql.SQL(statement).format(
                    database=database, migrator=migrator, app=app, backup=backup
                )
            )


def problems_with_app_account(cursor, *, require_encryption):
    """What is wrong with the account this cursor is connected as; empty when it is right."""
    problems = []
    cursor.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls"
        " FROM pg_roles WHERE rolname = current_user"
    )
    flags = dict(zip(PROBLEMS, cursor.fetchone(), strict=True))
    problems += [f"the account {text}" for key, text in PROBLEMS.items() if flags[key]]
    cursor.execute(
        "SELECT has_schema_privilege(current_user, 'public', 'CREATE'),"
        " has_database_privilege(current_user, current_database(), 'CREATE')"
    )
    can_create_in_schema, can_create_schema = cursor.fetchone()
    if can_create_in_schema:
        problems.append("the account can create tables")
    if can_create_schema:
        problems.append("the account can create schemas")
    if require_encryption:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
        row = cursor.fetchone()
        if not (row and row[0]):
            problems.append("the connection is not encrypted")
    return problems
