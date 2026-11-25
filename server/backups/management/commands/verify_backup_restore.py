from django.core.management.base import BaseCommand, CommandError

from backups.errors import DESCRIPTIONS, BackupFailure
from backups.restore_test import verify_restore


class Command(BaseCommand):
    help = (
        "Restore the newest backup into a throwaway database, check it, and delete it again. "
        "Run weekly by a timer."
    )

    def handle(self, *args, **options):
        try:
            run = verify_restore()
        except BackupFailure as failure:
            raise CommandError(f"The restore test failed: {DESCRIPTIONS[failure.kind]}.") from None
        self.stdout.write(f"Restore proven for {run.object_name}.")
