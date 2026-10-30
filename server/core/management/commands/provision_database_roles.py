import os

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand

from config.environment import require_settings
from config.secrets import looks_like_placeholder
from core.database_roles import Account, Accounts, provision_accounts
from core.errors import ConfigurationError


def accounts_in(accounts):
    return (accounts.app, accounts.migrator, accounts.backup)


class Command(BaseCommand):
    help = (
        "Create the app, migrator and backup database accounts and set their rights. "
        "Needs ADMIN_DATABASE_URL (an administrator account used for nothing else)."
    )

    def handle(self, *args, **options):
        urls = require_settings(
            ["ADMIN_DATABASE_URL", "DATABASE_URL", "MIGRATION_DATABASE_URL", "BACKUP_DATABASE_URL"],
            os.environ,
        )
        accounts = Accounts(
            app=Account.from_url("DATABASE_URL", urls["DATABASE_URL"]),
            migrator=Account.from_url("MIGRATION_DATABASE_URL", urls["MIGRATION_DATABASE_URL"]),
            backup=Account.from_url("BACKUP_DATABASE_URL", urls["BACKUP_DATABASE_URL"]),
        )
        development = settings.APP_ENV == "development"
        if not development:
            passwords = [account.password for account in accounts_in(accounts)]
            if any(looks_like_placeholder(password) for password in passwords):
                raise ConfigurationError(
                    "Set real passwords in the database addresses before creating the accounts.",
                    {
                        "placeholders": [
                            "DATABASE_URL",
                            "MIGRATION_DATABASE_URL",
                            "BACKUP_DATABASE_URL",
                        ]
                    },
                )
        database_name = settings.DATABASES["default"]["NAME"]
        with psycopg.connect(urls["ADMIN_DATABASE_URL"], autocommit=True) as connection:
            provision_accounts(connection, accounts, database_name, development=development)
        self.stdout.write("Database accounts are ready.")
