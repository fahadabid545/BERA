import os

from django.core.management.base import BaseCommand, CommandError

from backups.errors import DESCRIPTIONS, BackupFailure
from backups.format import DecryptingReader
from backups.keys import key_ring
from backups.store import get_store


class Command(BaseCommand):
    help = (
        "Decrypt a backup (the newest unless --name is given) into a dump file that pg_restore "
        "can read. For restoring after a loss; the file holds all the data: delete it afterwards."
    )

    def add_arguments(self, parser):
        parser.add_argument("output", help="Where to write the dump file (it must not exist).")
        parser.add_argument("--name", help="The backup's file name in the storage.")

    def handle(self, *args, output, name=None, **options):
        try:
            _, keys = key_ring()
            store = get_store()
            if name is None:
                newest = max(store.list(), key=lambda item: item.modified, default=None)
                if newest is None:
                    raise BackupFailure("no_backup")
                name = newest.name
            source = store.open(name)
            try:
                reader = DecryptingReader(source, keys)
                descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as target:
                    while chunk := reader.read(1024 * 1024):
                        target.write(chunk)
            finally:
                source.close()
        except BackupFailure as failure:
            raise CommandError(f"Could not decrypt: {DESCRIPTIONS[failure.kind]}.") from None
        except FileExistsError:
            raise CommandError("The output file already exists.") from None
        except OSError:
            raise CommandError("The backup could not be read or the file written.") from None
        self.stdout.write(f"Decrypted {name} to {output}.")
