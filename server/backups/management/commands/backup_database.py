from django.core.management.base import BaseCommand, CommandError

from backups.errors import DESCRIPTIONS, BackupFailure
from backups.service import run_backup


class Command(BaseCommand):
    help = "Back up the database to the backup storage, encrypted. Run daily by a timer."

    def handle(self, *args, **options):
        try:
            run = run_backup()
        except BackupFailure as failure:
            raise CommandError(f"The backup failed: {DESCRIPTIONS[failure.kind]}.") from None
        self.stdout.write(f"Backup saved: {run.object_name} ({run.size_bytes} bytes).")
