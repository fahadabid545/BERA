from django.core.management.base import BaseCommand, CommandError

from backups.freshness import check_backup_is_recent


class Command(BaseCommand):
    help = "Alert the super admins when no backup was made recently. Run hourly by a timer."

    def handle(self, *args, **options):
        if not check_backup_is_recent():
            raise CommandError("No recent backup.")
        self.stdout.write("A recent backup exists.")
