from django.core.management.base import BaseCommand
from django.db import connection

from core.development_only import require_development


class Command(BaseCommand):
    help = "Delete every table in the local development database."

    def handle(self, *args, **options):
        require_development()
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        self.stdout.write("Local database emptied.")
