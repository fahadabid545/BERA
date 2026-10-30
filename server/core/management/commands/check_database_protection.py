from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from config.secrets import REAL_ENVIRONMENTS
from core.database_roles import problems_with_app_account
from core.errors import ConfigurationError


class Command(BaseCommand):
    help = "Check that the account the app connects with is limited and its connection encrypted."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            problems = problems_with_app_account(
                cursor, require_encryption=settings.APP_ENV in REAL_ENVIRONMENTS
            )
        if problems:
            raise ConfigurationError(
                "The database connection is not protected enough.", {"problems": problems}
            )
        self.stdout.write("The database account and connection are protected.")
