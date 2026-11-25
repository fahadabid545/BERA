import pytest
from django.conf import settings as django_settings
from django.db import connection


@pytest.fixture(autouse=True)
def backup_settings(settings, tmp_path):
    """A local folder as the backup storage, fake keys, and the test database as the one that is
    backed up and the server that hosts the throwaway restore database."""
    settings.BACKUP_ENCRYPTION_KEY_ID = "k1"
    settings.BACKUP_ENCRYPTION_KEY = "test-only-backup-key-one-aaaa1111bbbb2222"
    settings.BACKUP_PREVIOUS_KEYS = ""
    settings.BACKUP_R2_BUCKET = ""
    settings.BACKUP_LOCAL_FOLDER = tmp_path / "backups"
    return settings


@pytest.fixture
def real_database(settings):
    """Points the backup and the restore test at the test database (a real pg_dump)."""
    parameters = connection.settings_dict
    address = (
        f"postgres://{parameters['USER']}:{parameters['PASSWORD']}"
        f"@{parameters['HOST'] or '127.0.0.1'}:{parameters['PORT'] or 5432}/"
    )
    settings.BACKUP_DATABASE_URL = f"{address}{parameters['NAME']}"
    settings.RESTORE_TEST_DATABASE_URL = f"{address}postgres"
    return django_settings
