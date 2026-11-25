import io
import os
from datetime import timedelta

import psycopg
import pytest
from botocore.exceptions import ClientError
from django.conf import settings as django_settings
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from audit.models import AuditEvent
from backups import service
from backups import store as stores
from backups.errors import BackupFailure
from backups.freshness import check_backup_is_recent
from backups.models import BackupRun
from backups.restore_test import verify_restore
from backups.store import LocalStore, StoredBackup, get_store, object_name
from companies.tests.test_invites import setting
from core.tests.factories import make_admin_user
from emailing.models import OutgoingEmail
from emailing.service import deliver_email

pytestmark = pytest.mark.django_db

OTHER_KEY = "test-only-backup-key-two-cccc3333dddd4444"


@pytest.fixture
def boss():
    return make_admin_user(role="super", email="boss@example.test", name="Fake Boss")


def stored_files():
    return sorted(path.name for path in get_store().folder.glob("bera-backup-*"))


def leftover_test_databases():
    url = django_settings.RESTORE_TEST_DATABASE_URL
    with psycopg.connect(url) as connection:
        rows = connection.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE 'bera_restore_test_%'"
        ).fetchall()
    return rows


def alert_text():
    emails = OutgoingEmail.objects.filter(template="security_alert")
    assert emails.count() == 1
    deliver_email(emails.get().pk)
    return mail.outbox[-1].body


def age(name, days):
    path = get_store().folder / name
    moment = (timezone.now() - timedelta(days=days)).timestamp()
    os.utime(path, (moment, moment))


class TestTheDailyBackup:
    def test_a_backup_is_saved_encrypted_and_recorded(self, real_database):
        run = service.run_backup()
        (name,) = stored_files()
        content = (get_store().folder / name).read_bytes()
        assert run.status == "succeeded" and run.object_name == name
        assert run.size_bytes == len(content) and run.encryption_key_id == "k1"
        assert b"PGDMP" not in content and b"django_migrations" not in content
        assert oct((get_store().folder / name).stat().st_mode & 0o777) == "0o600"

    def test_a_failed_dump_leaves_no_file_and_raises_the_alert(self, real_database, settings, boss):
        settings.BACKUP_DATABASE_URL = settings.BACKUP_DATABASE_URL.replace(
            "@", "x@", 1
        )  # a wrong password for the account
        with pytest.raises(BackupFailure) as caught:
            service.run_backup()
        assert caught.value.kind == "database_dump" and stored_files() == []
        run = BackupRun.objects.get()
        assert (run.status, run.failure_kind) == ("failed", "database_dump")
        entry = AuditEvent.objects.get(kind="security.backup_failed")
        assert entry.details == {"reason": "database_dump"}
        body = alert_text()
        assert "backup failed" in body and "could not be copied" in body
        assert "postgres://" not in body and settings.BACKUP_DATABASE_URL not in body

    def test_missing_settings_are_a_failure_not_a_crash(self, settings, boss):
        settings.BACKUP_ENCRYPTION_KEY = ""
        with pytest.raises(BackupFailure) as caught:
            service.run_backup()
        assert caught.value.kind == "configuration"
        assert BackupRun.objects.get().failure_kind == "configuration"

    def test_a_short_or_duplicate_key_is_refused(self, settings):
        settings.BACKUP_ENCRYPTION_KEY = "too-short"
        with pytest.raises(BackupFailure):
            service.run_backup()
        settings.BACKUP_ENCRYPTION_KEY = OTHER_KEY
        settings.BACKUP_PREVIOUS_KEYS = f"k1={OTHER_KEY}"
        with pytest.raises(BackupFailure):
            service.run_backup()

    def test_a_saved_file_of_the_wrong_size_is_removed_and_fails(self, real_database, monkeypatch):
        monkeypatch.setattr(LocalStore, "size", lambda self, name: 1)
        with pytest.raises(BackupFailure) as caught:
            service.run_backup()
        assert caught.value.kind == "upload" and stored_files() == []

    def test_an_unexpected_error_is_recorded_without_its_message(self, real_database, monkeypatch):
        def explode(*args):
            raise RuntimeError("postgres://u:fake-pw-0000@host/db")  # nosecret: fake

        monkeypatch.setattr(service, "_copy_to_storage", explode)
        with pytest.raises(BackupFailure) as caught:
            service.run_backup()
        assert caught.value.kind == "unexpected"
        assert "fake-pw-0000" not in str(list(BackupRun.objects.values()))
        assert "fake-pw-0000" not in str(list(AuditEvent.objects.values()))

    def test_the_command_succeeds_and_fails_with_an_exit_status(self, real_database, settings):
        call_command("backup_database")
        assert len(stored_files()) == 1
        settings.BACKUP_DATABASE_URL = settings.BACKUP_DATABASE_URL.replace("@", "x@", 1)
        with pytest.raises(CommandError):
            call_command("backup_database")


class TestRemovingOldBackups:
    def seed(self, ages):
        names = []
        for number, days in enumerate(ages):
            name = object_name(timezone.now() - timedelta(days=days, seconds=number))
            get_store().save(name, open_bytes(b"fake"))
            age(name, days)
            names.append(name)
        return names

    def test_backups_older_than_the_retention_are_removed_after_a_good_one(self, real_database):
        setting("backup.minimum_kept", 2)
        old = self.seed([40, 31, 5, 3])
        service.run_backup()
        left = stored_files()
        assert old[0] not in left and old[1] not in left
        assert old[2] in left and old[3] in left and len(left) == 3

    def test_the_retention_is_a_setting(self, real_database):
        setting("backup.minimum_kept", 1)
        setting("backup.retention_days", 3)
        old = self.seed([10, 4, 2])
        service.run_backup()
        assert old[0] not in stored_files() and old[1] not in stored_files()
        assert old[2] in stored_files()

    def test_nothing_is_removed_when_the_new_backup_fails(self, real_database, settings):
        old = self.seed([90, 60, 45])
        settings.BACKUP_DATABASE_URL = settings.BACKUP_DATABASE_URL.replace("@", "x@", 1)
        with pytest.raises(BackupFailure):
            service.run_backup()
        assert stored_files() == sorted(old)

    def test_the_newest_ones_stay_even_when_all_are_old(self, real_database):
        setting("backup.minimum_kept", 3)
        old = self.seed([100, 90, 80, 70, 60])
        service.remove_expired(get_store(), timezone.now())
        assert stored_files() == sorted(old[2:])

    def test_files_that_are_not_backups_are_never_touched(self, real_database):
        folder = get_store().folder
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "notes.txt").write_text("keep")
        age_path = folder / "notes.txt"
        os.utime(age_path, (1, 1))
        service.remove_expired(get_store(), timezone.now())
        assert (folder / "notes.txt").exists()

    def test_a_failure_to_remove_is_announced_but_the_backup_still_counts(
        self, real_database, monkeypatch, boss
    ):
        def refuse(store, now):
            raise RuntimeError("storage said no to secret-bucket")

        monkeypatch.setattr(service, "remove_expired", refuse)
        run = service.run_backup()
        assert run.status == "succeeded"
        assert AuditEvent.objects.get(kind="security.backup_failed").details == {
            "reason": "pruning"
        }


def open_bytes(data):
    return io.BytesIO(data)


class TestTheRestoreTest:
    def test_the_newest_backup_is_restored_checked_and_the_copy_deleted(self, real_database):
        service.run_backup()
        run = verify_restore()
        assert run.kind == "restore_test" and run.status == "succeeded"
        assert leftover_test_databases() == []

    def test_a_wrong_key_fails_and_the_alert_is_sent(self, real_database, settings, boss):
        service.run_backup()
        settings.BACKUP_ENCRYPTION_KEY = OTHER_KEY  # the key as configured now is not the one used
        with pytest.raises(BackupFailure) as caught:
            verify_restore()
        assert caught.value.kind == "decryption"
        run = BackupRun.objects.get(kind="restore_test")
        assert (run.status, run.failure_kind) == ("failed", "decryption")
        assert AuditEvent.objects.get(kind="security.restore_test_failed").details == {
            "reason": "decryption"
        }
        body = alert_text()
        assert "restores the latest backup failed" in body and "decrypted" in body
        assert OTHER_KEY not in body
        assert leftover_test_databases() == []

    def test_the_command_fails_with_an_exit_status_on_a_wrong_key(self, real_database, settings):
        service.run_backup()
        settings.BACKUP_ENCRYPTION_KEY = OTHER_KEY
        with pytest.raises(CommandError):
            call_command("verify_backup_restore")

    def test_after_a_key_change_the_older_backup_still_restores(self, real_database, settings):
        service.run_backup()
        settings.BACKUP_PREVIOUS_KEYS = f"k1={settings.BACKUP_ENCRYPTION_KEY}"
        settings.BACKUP_ENCRYPTION_KEY_ID = "k2"
        settings.BACKUP_ENCRYPTION_KEY = OTHER_KEY
        assert verify_restore().status == "succeeded"

    def test_with_no_backup_at_all_it_fails_and_says_so(self, real_database, boss):
        with pytest.raises(BackupFailure) as caught:
            verify_restore()
        assert caught.value.kind == "no_backup"
        assert "no backup to test" in alert_text()

    def test_a_cut_off_file_fails_and_leaves_no_test_database(self, real_database):
        service.run_backup()
        path = get_store().folder / stored_files()[0]
        path.write_bytes(path.read_bytes()[:-200])
        with pytest.raises(BackupFailure):
            verify_restore()
        assert leftover_test_databases() == []

    def test_a_restore_that_cannot_create_its_database_fails(self, real_database, settings):
        service.run_backup()
        settings.RESTORE_TEST_DATABASE_URL = settings.RESTORE_TEST_DATABASE_URL.replace(
            "@", "x@", 1
        )
        with pytest.raises(BackupFailure) as caught:
            verify_restore()
        assert caught.value.kind in {"restore", "unexpected"}

    def test_the_test_never_touches_the_real_database(self, real_database):
        service.run_backup()
        before = BackupRun.objects.count()
        verify_restore()
        assert BackupRun.objects.count() == before + 1  # the real database is unchanged


class TestTheLateAlert:
    def test_no_backup_ever_is_late(self, boss):
        assert check_backup_is_recent() is False
        assert AuditEvent.objects.get(kind="security.backup_late").details == {"reason": "late"}
        assert "No new database backup" in alert_text()

    def make_run(self, hours_ago, status="succeeded"):
        moment = timezone.now() - timedelta(hours=hours_ago)
        return BackupRun.objects.create(
            kind="backup", status=status, started_at=moment, finished_at=moment
        )

    def test_a_backup_within_26_hours_is_fine(self, boss):
        self.make_run(25)
        assert check_backup_is_recent() is True
        assert not AuditEvent.objects.filter(kind="security.backup_late").exists()

    def test_a_backup_older_than_26_hours_is_late(self, boss):
        self.make_run(27)
        assert check_backup_is_recent() is False

    def test_only_successful_backups_count(self, boss):
        self.make_run(1, status="failed")
        assert check_backup_is_recent() is False

    def test_the_limit_is_a_setting(self, boss):
        setting("backup.late_after_hours", 48)
        self.make_run(30)
        assert check_backup_is_recent() is True

    def test_the_alert_goes_out_once_per_cooldown(self, boss):
        check_backup_is_recent()
        check_backup_is_recent()
        assert OutgoingEmail.objects.filter(template="security_alert").count() == 1

    def test_the_command_fails_when_late(self, boss):
        with pytest.raises(CommandError):
            call_command("check_backup_fresh")
        self.make_run(1)
        call_command("check_backup_fresh")


class FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def _maybe_fail(self):
        if self.error:
            raise self.error

    def upload_fileobj(self, source, bucket, name, Config):
        self._maybe_fail()
        self.calls.append(("upload", bucket, name, source.read()))

    def head_object(self, Bucket, Key):
        self._maybe_fail()
        return {"ContentLength": 4}

    def get_object(self, Bucket, Key):
        self._maybe_fail()
        return {"Body": open_bytes(b"data")}

    def delete_object(self, Bucket, Key):
        self._maybe_fail()
        self.calls.append(("delete", Bucket, Key))

    def get_paginator(self, name):
        client = self

        class Pages:
            def paginate(self, Bucket):
                client._maybe_fail()
                yield {
                    "Contents": [
                        {
                            "Key": "bera-backup-20260101T020000Z.dump.enc",
                            "LastModified": timezone.now(),
                            "Size": 5,
                        },
                        {"Key": "something-else.txt", "LastModified": timezone.now(), "Size": 1},
                    ]
                }

        return Pages()


class TestTheR2Store:
    def test_files_go_to_the_backup_bucket_only(self):
        client = FakeClient()
        store = stores.R2Store(client, "fake-backup-bucket")
        store.save("bera-backup-20260101T020000Z.dump.enc", open_bytes(b"abc"))
        store.delete("bera-backup-20260101T020000Z.dump.enc")
        assert client.calls[0][:3] == (
            "upload",
            "fake-backup-bucket",
            "bera-backup-20260101T020000Z.dump.enc",
        )
        assert client.calls[1][1] == "fake-backup-bucket"

    def test_the_list_holds_only_backup_files(self):
        found = stores.R2Store(FakeClient(), "fake-backup-bucket").list()
        assert [item.name for item in found] == ["bera-backup-20260101T020000Z.dump.enc"]
        assert isinstance(found[0], StoredBackup)

    @pytest.mark.parametrize(
        ("call", "kind"),
        [
            (lambda s: s.save("n", open_bytes(b"")), "upload"),
            (lambda s: s.size("n"), "storage"),
            (lambda s: s.open("n"), "download"),
            (lambda s: s.list(), "storage"),
            (lambda s: s.delete("n"), "pruning"),
        ],
    )
    def test_storage_errors_become_a_kind_without_their_message(self, call, kind):
        error = ClientError({"Error": {"Code": "AccessDenied", "Message": "secret-detail"}}, "x")
        with pytest.raises(BackupFailure) as caught:
            call(stores.R2Store(FakeClient(error), "fake-backup-bucket"))
        assert caught.value.kind == kind and "secret-detail" not in str(caught.value)


class TestChoosingTheStore:
    def test_a_bucket_means_r2(self, settings, monkeypatch):
        settings.BACKUP_R2_BUCKET = "fake-backup-bucket"
        monkeypatch.setattr(stores, "_r2_client", lambda: FakeClient())
        assert isinstance(get_store(), stores.R2Store)

    def test_development_may_use_a_folder(self):
        assert isinstance(get_store(), LocalStore)

    def test_staging_and_production_never_fall_back_to_a_folder(self, settings):
        settings.APP_ENV = "production"
        with pytest.raises(BackupFailure) as caught:
            get_store()
        assert caught.value.kind == "configuration"


class TestDecryptingForARestore:
    def test_the_newest_backup_is_written_as_a_dump_pg_restore_reads(self, real_database, tmp_path):
        service.run_backup()
        target = tmp_path / "plain.dump"
        call_command("decrypt_backup", str(target))
        assert target.read_bytes().startswith(b"PGDMP")
        assert oct(target.stat().st_mode & 0o777) == "0o600"

    def test_it_never_overwrites_a_file(self, real_database, tmp_path):
        service.run_backup()
        target = tmp_path / "plain.dump"
        target.write_bytes(b"keep")
        with pytest.raises(CommandError):
            call_command("decrypt_backup", str(target))
        assert target.read_bytes() == b"keep"

    def test_a_wrong_key_writes_nothing_useful_and_says_why(
        self, real_database, settings, tmp_path
    ):
        service.run_backup()
        settings.BACKUP_ENCRYPTION_KEY = OTHER_KEY
        with pytest.raises(CommandError, match="decrypted"):
            call_command("decrypt_backup", str(tmp_path / "plain.dump"))

    def test_with_no_backup_it_says_so(self, tmp_path):
        with pytest.raises(CommandError, match="no backup"):
            call_command("decrypt_backup", str(tmp_path / "plain.dump"))
