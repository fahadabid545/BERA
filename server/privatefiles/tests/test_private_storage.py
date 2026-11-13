import os
import stat
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.utils import timezone

import privatefiles
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from privatefiles import local, r2
from privatefiles.errors import InvalidLink, StorageError, StorageUnavailable, StoredFileMissing

pytestmark = pytest.mark.django_db


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    waits = []
    monkeypatch.setattr("privatefiles.service.time.sleep", waits.append)
    return waits


class TestLocalStore:
    def test_a_file_can_be_saved_read_and_removed(self):
        privatefiles.save_file("cvs/1/a", b"hello")
        assert privatefiles.read_file("cvs/1/a") == b"hello"
        privatefiles.delete_file("cvs/1/a")
        with pytest.raises(StoredFileMissing):
            privatefiles.read_file("cvs/1/a")

    def test_removing_a_missing_file_is_fine(self):
        privatefiles.delete_file("cvs/none/none")

    def test_saving_again_replaces_the_file(self):
        privatefiles.save_file("cvs/1/a", b"one")
        privatefiles.save_file("cvs/1/a", b"two")
        assert privatefiles.read_file("cvs/1/a") == b"two"

    @pytest.mark.parametrize("key", ["../outside", "cvs/../../outside", "/etc/passwd"])
    def test_a_key_cannot_leave_the_storage_folder(self, key):
        with pytest.raises(ValueError):
            privatefiles.save_file(key, b"x")

    def test_files_and_folders_are_private_to_the_app(self, settings):
        privatefiles.save_file("cvs/1/a", b"x")
        file_path = settings.PRIVATE_FILES_ROOT / "cvs/1/a"
        assert stat.S_IMODE(os.stat(file_path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(file_path.parent).st_mode) == 0o700

    def test_the_folder_is_not_under_anything_the_web_server_serves(self, settings):
        from pathlib import Path

        for served in ("static", "media", "public"):
            assert served not in Path(settings.PRIVATE_FILES_ROOT).parts

    def test_the_key_is_built_from_ids_only(self):
        assert privatefiles.key_for_cv(3, "abc") == "cvs/3/abc"


class TestRetries:
    def test_a_failed_attempt_is_tried_again_after_the_configured_waits(
        self, monkeypatch, no_waiting
    ):
        attempts = []

        def flaky(key, data):
            attempts.append(1)
            if len(attempts) < 3:
                raise StorageError

        monkeypatch.setattr(local, "save", flaky)
        privatefiles.save_file("cvs/1/a", b"x")
        assert len(attempts) == 3
        assert no_waiting == [1, 3]

    def test_when_the_waits_run_out_the_failure_is_reported(self, monkeypatch, no_waiting):
        def always(key, data):
            raise StorageError

        monkeypatch.setattr(local, "save", always)
        with pytest.raises(StorageUnavailable) as caught:
            privatefiles.save_file("cvs/1/a", b"x")
        assert caught.value.code == "storage_unavailable"
        assert caught.value.status_code == 503
        assert no_waiting == [1, 3]

    def test_the_waits_come_from_platform_settings(self, monkeypatch, no_waiting):
        set_setting("storage.retry_waits_seconds", [5])

        def always(key):
            raise StorageError

        monkeypatch.setattr(local, "delete", always)
        with pytest.raises(StorageUnavailable):
            privatefiles.delete_file("cvs/1/a")
        assert no_waiting == [5]

    def test_a_missing_file_is_not_retried(self, no_waiting):
        with pytest.raises(StoredFileMissing):
            privatefiles.read_file("cvs/1/none")
        assert no_waiting == []

    def test_the_message_for_people_leaks_nothing(self):
        assert "File storage is not reachable" in StorageUnavailable().message


class TestLocalLinks:
    def test_a_link_gives_the_file_back_with_its_clean_name(self):
        privatefiles.save_file("cvs/1/a", b"hello")
        link = privatefiles.download_link("cvs/1/a", "jane-cv.pdf")
        assert link["url"].startswith("/api/files/")
        token = link["url"].split("/")[3]
        assert privatefiles.read_for_link(token) == (b"hello", "jane-cv.pdf")

    def test_the_link_works_for_24_hours_by_default(self):
        link = privatefiles.download_link("cvs/1/a", "a.pdf")
        from datetime import datetime

        expires = datetime.fromisoformat(link["expires_at"])
        assert timedelta(hours=23, minutes=59) < expires - timezone.now() <= timedelta(hours=24)

    def test_an_expired_link_stops_working(self, monkeypatch):
        privatefiles.save_file("cvs/1/a", b"hello")
        token = privatefiles.download_link("cvs/1/a", "a.pdf")["url"].split("/")[3]
        import time

        real = time.time
        monkeypatch.setattr("django.core.signing.time.time", lambda: real() + 24 * 3600 + 60)
        with pytest.raises(InvalidLink) as caught:
            privatefiles.read_for_link(token)
        assert caught.value.status_code == 403

    def test_a_link_still_works_just_before_it_expires(self, monkeypatch):
        privatefiles.save_file("cvs/1/a", b"hello")
        token = privatefiles.download_link("cvs/1/a", "a.pdf")["url"].split("/")[3]
        import time

        real = time.time
        monkeypatch.setattr("django.core.signing.time.time", lambda: real() + 24 * 3600 - 60)
        assert privatefiles.read_for_link(token)[0] == b"hello"

    def test_the_lifetime_comes_from_platform_settings(self):
        set_setting("storage.download_link_hours", 1)
        link = privatefiles.download_link("cvs/1/a", "a.pdf")
        from datetime import datetime

        assert datetime.fromisoformat(link["expires_at"]) - timezone.now() <= timedelta(hours=1)

    @pytest.mark.parametrize("token", ["", "garbage", "a:b:c", "x" * 200])
    def test_a_made_up_link_is_refused(self, token):
        with pytest.raises(InvalidLink):
            privatefiles.read_for_link(token)

    def test_a_changed_link_is_refused(self):
        token = privatefiles.download_link("cvs/1/a", "a.pdf")["url"].split("/")[3]
        with pytest.raises(InvalidLink):
            privatefiles.read_for_link(token[:-3] + ("abc" if token[-3:] != "abc" else "xyz"))

    def test_a_link_for_another_purpose_is_refused(self):
        from django.core import signing

        other = signing.dumps({"key": "cvs/1/a", "name": "a.pdf"}, salt="something-else")
        with pytest.raises(InvalidLink):
            privatefiles.read_for_link(other)


class FakeBucket:
    """Stands in for R2: remembers objects and what it was asked."""

    def __init__(self):
        self.objects = {}
        self.calls = []

    def put_object(self, Bucket, Key, Body):
        self.calls.append(("put", Bucket, Key))
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        import io

        from botocore.exceptions import ClientError

        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def generate_presigned_url(self, *args, **kwargs):
        """Signing needs no network, so the real library signs with the test credentials."""
        import boto3
        from botocore.config import Config

        real = boto3.client(
            "s3",
            endpoint_url="https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
            aws_access_key_id="test-only-key-id",
            aws_secret_access_key="test-only-secret-key-value",
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
        return real.generate_presigned_url(*args, **kwargs)

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete", Bucket, Key))
        self.objects.pop(Key, None)


@pytest.fixture
def on_r2(settings, monkeypatch):
    settings.FILE_STORAGE_BACKEND = "r2"
    settings.R2_ACCOUNT_ID = "0123456789abcdef0123456789abcdef"
    settings.R2_ACCESS_KEY_ID = "test-only-key-id"
    settings.R2_SECRET_ACCESS_KEY = "test-only-secret-key-value"
    settings.R2_BUCKET = "bera-test-bucket"
    bucket = FakeBucket()
    monkeypatch.setattr(r2, "make_client", lambda: bucket)
    return bucket


class TestR2Store:
    def test_files_go_to_the_private_bucket_and_not_the_local_folder(self, on_r2, settings):
        privatefiles.save_file("cvs/1/a", b"hello")
        assert on_r2.objects == {"cvs/1/a": b"hello"}
        assert ("put", "bera-test-bucket", "cvs/1/a") in on_r2.calls
        assert not settings.PRIVATE_FILES_ROOT.exists()

    def test_reading_and_removing(self, on_r2):
        privatefiles.save_file("cvs/1/a", b"hello")
        assert privatefiles.read_file("cvs/1/a") == b"hello"
        privatefiles.delete_file("cvs/1/a")
        assert on_r2.objects == {}
        with pytest.raises(StoredFileMissing):
            privatefiles.read_file("cvs/1/a")

    def test_a_provider_failure_is_retried_then_reported(self, on_r2, no_waiting):
        from botocore.exceptions import ClientError

        def down(**kwargs):
            raise ClientError({"Error": {"Code": "503"}}, "PutObject")

        on_r2.put_object = down
        with pytest.raises(StorageUnavailable):
            privatefiles.save_file("cvs/1/a", b"x")
        assert no_waiting == [1, 3]

    def test_the_link_is_a_signed_address_that_lasts_24_hours(self, on_r2):
        link = privatefiles.download_link("cvs/1/a", "jane-cv.pdf")
        parsed = urlparse(link["url"])
        query = parse_qs(parsed.query)
        assert (
            parsed.hostname
            == "bera-test-bucket.0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
            or parsed.hostname.endswith("r2.cloudflarestorage.com")
        )
        assert "cvs/1/a" in parsed.path
        assert query["X-Amz-Expires"] == ["86400"]
        assert "X-Amz-Signature" in query
        assert 'filename="jane-cv.pdf"' in query["response-content-disposition"][0]

    def test_the_link_never_contains_the_secret_key(self, on_r2):
        link = privatefiles.download_link("cvs/1/a", "a.pdf")
        assert "test-only-secret-key-value" not in link["url"]


class TestDeletionRemovesFilesFromTheStore:
    def test_deleting_a_project_removes_its_files_from_r2(self, on_r2):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils import timezone
        from rest_framework.test import APIClient

        from core.tests.factories import make_company, make_company_user, start_session_for
        from cvs.models import CvFile
        from cvs.tests.files import make_pdf
        from plans import subscriptions as subs
        from plans.models import Plan
        from projects.models import Project

        company = make_company()
        now = timezone.now()
        plan = Plan.objects.create(
            name="Basic",
            status="active",
            price_usd=10,
            cvs_per_month=100,
            cvs_per_project=50,
            max_projects=5,
            max_team_accounts=3,
            max_top_n=10,
            monthly_ai_token_cap=10000,
        )
        subs.activate(company.pk, plan, period_start=now, period_end=now + timedelta(days=30))
        owner = make_company_user(company)
        project = Project.objects.create(
            company=company,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=owner,
        )
        issued = start_session_for(
            user_id=owner.pk, role="owner", company_id=company.pk, kind="company"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        client.post(
            f"/api/company/projects/{project.pk}/cvs/",
            {"files": [SimpleUploadedFile("a.pdf", make_pdf())]},
            format="multipart",
        )
        assert len(on_r2.objects) == 1
        response = client.delete(
            f"/api/company/projects/{project.pk}/", {"confirm_title": "T"}, format="json"
        )
        assert response.status_code == 204
        assert on_r2.objects == {}
        assert not CvFile.objects.exists()

    def test_if_the_store_cannot_delete_nothing_is_deleted(self, on_r2, no_waiting):
        from botocore.exceptions import ClientError

        from core.tests.factories import make_company, make_company_user
        from cvs.models import CvFile
        from cvs.service import remove_cv_file
        from projects.models import Project

        company = make_company()
        owner = make_company_user(company)
        project = Project.objects.create(
            company=company,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=owner,
        )
        cv = CvFile.objects.create(
            company=company,
            project=project,
            original_name="a.pdf",
            file_type="pdf",
            size_bytes=1,
            storage_key="cvs/x/y",
            uploaded_by=owner,
        )
        on_r2.delete_object = lambda **kwargs: (_ for _ in ()).throw(
            ClientError({"Error": {"Code": "503"}}, "DeleteObject")
        )
        with pytest.raises(StorageUnavailable):
            remove_cv_file(cv)
        assert CvFile.objects.filter(pk=cv.pk).exists()
