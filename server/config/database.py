"""Which database account a process uses, and the rules for its connection.

Three accounts exist (see core/database_roles.py). The running app and its workers use the
`app` account, which cannot change the database structure. Commands that do change it
(`migrate`...) run in the `migrations` role with the more privileged migrator account. A
process never holds the other account's password.
"""

import os
from urllib.parse import parse_qs, urlsplit

from core.errors import ConfigurationError

DATABASE_ROLES = ("app", "migrations")
URL_SETTING_BY_ROLE = {"app": "DATABASE_URL", "migrations": "MIGRATION_DATABASE_URL"}
# Commands that create or change tables, or set the accounts' rights.
SCHEMA_COMMANDS = ("migrate", "reset_dev_db", "provision_database_roles")
# `require` encrypts; the verify modes also prove the server is the right one (the goal).
ENCRYPTED_SSL_MODES = ("require", "verify-ca", "verify-full")


def database_role(environ=os.environ):
    role = environ.get("DATABASE_ROLE", "app").strip() or "app"
    if role not in DATABASE_ROLES:
        raise ConfigurationError(
            f"DATABASE_ROLE must be one of {', '.join(DATABASE_ROLES)}.",
            {"allowed": list(DATABASE_ROLES)},
        )
    return role


def require_encrypted_connection(environ, app_env, role):
    """In staging and production the database address must demand an encrypted connection."""
    if app_env == "development":
        return
    setting = URL_SETTING_BY_ROLE[role]
    url = environ.get(setting, "").strip()
    modes = parse_qs(urlsplit(url).query).get("sslmode", [""])
    if modes[-1] not in ENCRYPTED_SSL_MODES:
        raise ConfigurationError(
            f"{setting} must end with ?sslmode=verify-full (or verify-ca, require) "
            "so the database connection is encrypted.",
            {"unencrypted": [setting], "allowed": list(ENCRYPTED_SSL_MODES)},
        )
