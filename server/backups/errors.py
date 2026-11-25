"""What can go wrong with a backup, named by kind only.

The kind is all that reaches the audit log and the alert email, so nothing about the data, the
database or the storage can leak through them. `DESCRIPTIONS` is the plain wording for each.
"""

from core.errors import AppError

DESCRIPTIONS = {
    "configuration": "a backup setting is missing or wrong",
    "database_dump": "the database could not be copied",
    "upload": "the copy could not be saved to the backup storage",
    "storage": "the backup storage could not be reached",
    "no_backup": "there was no backup to test",
    "download": "the backup could not be read back from the storage",
    "decryption": "the backup could not be decrypted with the configured key",
    "restore": "the backup could not be restored into a test database",
    "verification": "the restored test database did not look complete",
    "cleanup": "the temporary test database could not be removed",
    "pruning": "old backups could not be removed",
    "unexpected": "something unexpected went wrong",
}


class BackupFailure(AppError):
    """A backup step failed. `kind` is one of the keys of DESCRIPTIONS."""

    status_code = 500

    def __init__(self, kind):
        assert kind in DESCRIPTIONS, kind
        super().__init__("backup_failed", f"The backup step failed ({kind}).", {"kind": kind})
        self.kind = kind
