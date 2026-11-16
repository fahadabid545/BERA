import io
import zipfile
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

import privatefiles
from activity.models import ActivityEntry
from core.tests.factories import make_company_user, start_session_for
from cvs import download_packages
from cvs.models import Candidate, CvFile, DownloadPackage
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add
from emailing.models import OutgoingEmail
from platform_settings.service import get_setting
from projects import deletion

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def stored(tenant, name, score=70, **fields):
    """A scored CV whose file is really in storage, so it can go into a zip."""
    row = add(tenant, name, score, **fields)
    privatefiles.save_file(row.storage_key, f"bytes of {name}".encode())
    return row


def sign_in(person, role="member"):
    issued = start_session_for(
        user_id=person.pk, role=role, company_id=person.company_id, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def downloads_url(tenant):
    return f"/api/company/projects/{tenant.project.pk}/downloads/"


def ask(tenant, body):
    return tenant.client.post(downloads_url(tenant), body, format="json")


def package_url(package_id, suffix=""):
    return f"/api/company/downloads/{package_id}/{suffix}"


def zip_names(response):
    return sorted(zipfile.ZipFile(io.BytesIO(response.content)).namelist())


def candidates_of(*names):
    """The ids of the candidates whose CVs have these file names."""
    found = Candidate.objects.filter(cv_file__original_name__in=names)
    return [str(candidate.pk) for candidate in found]


@pytest.fixture
def three(tenant):
    stored(tenant, "a.pdf", 90, minutes=1)
    stored(tenant, "b.pdf", 70, minutes=2)
    stored(tenant, "c.pdf", 50, minutes=3)
    return tenant


class TestSmallPackages:
    def test_all_cvs_of_the_project_are_ready_at_once(self, three):
        response = ask(three, {"all": True})
        assert response.status_code == 201
        body = response.json()
        assert (body["status"], body["files"]) == ("ready", 3)
        assert body["expires_at"] and body["size_bytes"]
        file = three.client.get(package_url(body["id"], "file/"))
        assert file.status_code == 200 and file["Content-Type"] == "application/zip"
        assert "attachment" in file["Content-Disposition"]
        assert file["Cache-Control"] == "private, no-store"
        assert zip_names(file) == ["a.pdf", "b.pdf", "c.pdf"]

    def test_the_zip_holds_the_real_files(self, three):
        body = ask(three, {"all": True}).json()
        file = three.client.get(package_url(body["id"], "file/"))
        archive = zipfile.ZipFile(io.BytesIO(file.content))
        assert archive.read("a.pdf") == b"bytes of a.pdf"

    def test_chosen_cvs_only(self, three):
        body = ask(three, {"candidate_ids": candidates_of("a.pdf", "c.pdf")}).json()
        assert body["files"] == 2
        file = three.client.get(package_url(body["id"], "file/"))
        assert zip_names(file) == ["a.pdf", "c.pdf"]

    def test_one_cv_can_be_a_package_too(self, three):
        body = ask(three, {"candidate_ids": candidates_of("b.pdf")}).json()
        assert body["files"] == 1

    def test_rejected_candidates_are_in_all_but_cancelled_cvs_are_not(self, three):
        stored(three, "rejected.pdf", 10, minutes=4)
        Candidate.objects.filter(cv_file__original_name="rejected.pdf").update(stage="rejected")
        stored(three, "cancelled.pdf", None, status="cancelled", minutes=5)
        body = ask(three, {"all": True}).json()
        file = three.client.get(package_url(body["id"], "file/"))
        assert "rejected.pdf" in zip_names(file) and "cancelled.pdf" not in zip_names(file)

    def test_two_files_with_one_name_are_both_kept(self, tenant):
        first = stored(tenant, "same.pdf", 80, minutes=1)
        second = stored(tenant, "dir/other.pdf", 70, minutes=2)
        CvFile.objects.filter(pk=second.pk).update(original_name="same.pdf")
        assert first.pk != second.pk
        body = ask(tenant, {"all": True}).json()
        file = tenant.client.get(package_url(body["id"], "file/"))
        assert zip_names(file) == ["same (2).pdf", "same.pdf"]

    def test_a_name_with_folders_is_flattened(self, tenant):
        row = stored(tenant, "x.pdf", 80)
        CvFile.objects.filter(pk=row.pk).update(original_name="../../etc/passwd.pdf")
        body = ask(tenant, {"all": True}).json()
        file = tenant.client.get(package_url(body["id"], "file/"))
        assert zip_names(file) == ["passwd.pdf"]

    def test_no_email_is_sent_for_a_small_package(self, three):
        ask(three, {"all": True})
        assert not OutgoingEmail.objects.filter(template="download_ready").exists()


class TestWhatCanBeAskedFor:
    @pytest.mark.parametrize(
        "body", [{}, {"candidate_ids": []}, {"candidate_ids": "x"}, {"candidate_ids": ["nope"]}]
    )
    def test_a_bad_choice_is_refused(self, three, body):
        response = ask(three, body)
        assert response.status_code == 400
        assert "candidate_ids" in response.json()["error"]["fields"]

    def test_a_cv_of_another_project_is_refused(self, three):
        stored(Tenant(make_plan()), "z.pdf")
        response = ask(three, {"candidate_ids": candidates_of("z.pdf")})
        assert response.status_code == 400 and not DownloadPackage.objects.exists()

    def test_a_project_with_no_cvs_has_nothing_to_download(self, tenant):
        response = ask(tenant, {"all": True})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "nothing_to_download"

    def test_another_companys_project_is_not_found(self, three):
        outsider = Tenant(make_plan())
        response = outsider.client.post(downloads_url(three), {"all": True}, format="json")
        assert response.status_code == 404

    def test_signing_in_is_needed(self, three):
        assert (
            APIClient().post(downloads_url(three), {"all": True}, format="json").status_code == 401
        )


class TestLargePackages:
    @pytest.fixture
    def queued(self, three, monkeypatch):
        set_setting("downloads.background_over_files", 2)
        calls = []
        monkeypatch.setattr(download_packages, "async_task", lambda job, *a: calls.append((job, a)))
        return three, calls

    def test_more_files_than_the_limit_wait_for_the_background_job(self, queued):
        tenant, calls = queued
        body = ask(tenant, {"all": True}).json()
        assert body["status"] == "preparing" and body["expires_at"] is None
        assert calls == [(download_packages.BUILD_JOB, (body["id"],))]

    def test_exactly_the_limit_is_still_made_at_once(self, queued):
        tenant, calls = queued
        body = ask(tenant, {"candidate_ids": candidates_of("a.pdf", "b.pdf")}).json()
        assert body["status"] == "ready" and calls == []

    def test_it_cannot_be_downloaded_before_it_is_ready(self, queued):
        tenant, _ = queued
        body = ask(tenant, {"all": True}).json()
        response = tenant.client.get(package_url(body["id"], "file/"))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "package_not_ready"

    def test_the_job_makes_it_and_emails_only_a_link_to_the_app(self, queued):
        tenant, _ = queued
        body = ask(tenant, {"all": True}).json()
        download_packages.build_package(body["id"])
        assert tenant.client.get(package_url(body["id"])).json()["status"] == "ready"
        email = OutgoingEmail.objects.get(template="download_ready")
        assert email.to_address == tenant.owner.email
        assert f"/company/downloads/{body['id']}" in email.text_body
        assert "24 hours" in email.text_body
        for forbidden in ("a.pdf", "b.pdf", "c.pdf", "Jane", "/api/", ".zip"):
            assert forbidden not in email.text_body + email.html_body

    def test_the_email_is_sent_once_even_if_the_job_runs_twice(self, queued):
        tenant, _ = queued
        body = ask(tenant, {"all": True}).json()
        download_packages.build_package(body["id"])
        download_packages.build_package(body["id"])
        assert OutgoingEmail.objects.filter(template="download_ready").count() == 1

    def test_the_zip_from_the_job_downloads(self, queued):
        tenant, _ = queued
        body = ask(tenant, {"all": True}).json()
        download_packages.build_package(body["id"])
        file = tenant.client.get(package_url(body["id"], "file/"))
        assert zip_names(file) == ["a.pdf", "b.pdf", "c.pdf"]

    def test_a_missing_file_fails_the_package_and_sends_nothing(self, queued):
        tenant, _ = queued
        privatefiles.delete_file(CvFile.objects.get(original_name="b.pdf").storage_key)
        body = ask(tenant, {"all": True}).json()
        download_packages.build_package(body["id"])
        assert tenant.client.get(package_url(body["id"])).json()["status"] == "failed"
        assert tenant.client.get(package_url(body["id"], "file/")).status_code == 409
        assert not OutgoingEmail.objects.filter(template="download_ready").exists()

    def test_a_cv_removed_meanwhile_fails_the_package(self, queued):
        tenant, _ = queued
        body = ask(tenant, {"all": True}).json()
        CvFile.objects.filter(original_name="c.pdf").delete()
        download_packages.build_package(body["id"])
        assert tenant.client.get(package_url(body["id"])).json()["status"] == "failed"


class TestStatus:
    def test_the_status_names_how_often_to_look_again(self, three):
        body = ask(three, {"all": True}).json()
        status = three.client.get(package_url(body["id"])).json()
        assert status["refresh_seconds"] == get_setting("live_updates.max_delay_seconds")
        assert status["project_id"] == str(three.project.pk)


class TestExpiry:
    def test_it_lasts_the_set_number_of_hours(self, three):
        set_setting("sharing.download_package_link_hours", 5)
        package = DownloadPackage.objects.get(pk=ask(three, {"all": True}).json()["id"])
        assert timedelta(hours=4, minutes=59) < package.expires_at - package.ready_at
        assert package.expires_at - package.ready_at <= timedelta(hours=5)

    def test_an_expired_package_is_refused(self, three):
        body = ask(three, {"all": True}).json()
        DownloadPackage.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        assert three.client.get(package_url(body["id"])).json()["status"] == "expired"
        response = three.client.get(package_url(body["id"], "file/"))
        assert response.status_code == 410
        assert response.json()["error"]["code"] == "package_expired"

    def test_the_job_removes_the_files_of_expired_packages_only(self, three):
        old = DownloadPackage.objects.get(pk=ask(three, {"all": True}).json()["id"])
        fresh = DownloadPackage.objects.get(pk=ask(three, {"all": True}).json()["id"])
        DownloadPackage.objects.filter(pk=old.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert download_packages.remove_expired_packages() == 1
        old.refresh_from_db()
        assert old.status == "expired" and old.storage_key == ""
        with pytest.raises(privatefiles.StoredFileMissing):
            privatefiles.read_file(privatefiles.key_for_package(old.company_id, old.pk))
        assert privatefiles.read_file(fresh.storage_key)
        assert download_packages.remove_expired_packages() == 0

    def test_a_file_already_gone_is_expired_not_an_error(self, three):
        body = ask(three, {"all": True}).json()
        package = DownloadPackage.objects.get(pk=body["id"])
        privatefiles.delete_file(package.storage_key)
        response = three.client.get(package_url(body["id"], "file/"))
        assert response.status_code == 410


class TestWhoMayDownload:
    def test_a_colleague_cannot_see_or_download_it(self, three):
        body = ask(three, {"all": True}).json()
        colleague = sign_in(make_company_user(three.company, role="member"))
        assert colleague.get(package_url(body["id"])).status_code == 404
        assert colleague.get(package_url(body["id"], "file/")).status_code == 404

    def test_another_company_cannot(self, three):
        body = ask(three, {"all": True}).json()
        outsider = Tenant(make_plan())
        assert outsider.client.get(package_url(body["id"])).status_code == 404
        assert outsider.client.get(package_url(body["id"], "file/")).status_code == 404

    def test_a_member_may_make_and_download_their_own(self, three):
        member = sign_in(make_company_user(three.company, role="member"))
        body = member.post(downloads_url(three), {"all": True}, format="json").json()
        assert member.get(package_url(body["id"], "file/")).status_code == 200

    def test_signing_in_is_needed(self, three):
        body = ask(three, {"all": True}).json()
        assert APIClient().get(package_url(body["id"], "file/")).status_code == 401

    def test_an_unknown_or_malformed_id_is_not_found(self, three):
        assert three.client.get(package_url("not-an-id")).status_code == 404
        assert (
            three.client.get(package_url("00000000-0000-0000-0000-000000000000")).status_code == 404
        )


class TestLogging:
    def entries(self, tenant):
        return list(ActivityEntry.objects.filter(company=tenant.company, kind="download"))

    def test_downloading_a_package_is_logged_with_its_size_in_files(self, three):
        body = ask(three, {"all": True}).json()
        assert self.entries(three) == []  # asking is not downloading
        three.client.get(package_url(body["id"], "file/"))
        (entry,) = self.entries(three)
        assert entry.details == {"scope": "package", "files": 3}
        assert (entry.target_kind, entry.target_id) == ("project", str(three.project.pk))
        assert entry.actor_id == three.owner.pk

    def test_each_download_of_the_same_package_is_logged(self, three):
        body = ask(three, {"all": True}).json()
        for _ in range(2):
            three.client.get(package_url(body["id"], "file/"))
        assert len(self.entries(three)) == 2

    def test_a_refused_download_is_not_logged(self, three):
        body = ask(three, {"all": True}).json()
        DownloadPackage.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        three.client.get(package_url(body["id"], "file/"))
        assert self.entries(three) == []

    def test_one_cv_download_is_logged_but_showing_it_in_the_page_is_not(self, three):
        candidate = (
            three.project.candidates.first() if hasattr(three.project, "candidates") else None
        )
        candidate = Candidate.objects.filter(project=three.project).first()
        base = f"/api/company/projects/{three.project.pk}/candidates/{candidate.pk}/cv/"
        three.client.get(base)
        assert self.entries(three) == []
        three.client.get(base + "?download=1")
        (entry,) = self.entries(three)
        assert entry.details == {"scope": "cv", "files": 1}

    def test_the_log_holds_no_names(self, three):
        body = ask(three, {"all": True}).json()
        three.client.get(package_url(body["id"], "file/"))
        text = str(self.entries(three)[0].details)
        assert ".pdf" not in text and "Jane" not in text


class TestLimits:
    def test_the_download_rate_limit_applies(self, three):
        set_setting("rate_limits.downloads_per_minute", 2)
        first = ask(three, {"all": True})
        second = three.client.get(package_url(first.json()["id"], "file/"))
        third = three.client.get(package_url(first.json()["id"], "file/"))
        assert (first.status_code, second.status_code, third.status_code) == (201, 200, 429)

    def test_many_downloads_raise_the_volume_alert_once(self, three):
        from audit.models import AuditEvent

        set_setting("security.download_alert_threshold", 4)
        body = ask(three, {"all": True}).json()
        for _ in range(3):
            three.client.get(package_url(body["id"], "file/"))
        assert AuditEvent.objects.filter(kind="security.download_volume").count() == 1


class TestProjectDeletion:
    def test_deleting_the_project_removes_its_packages_and_their_files(self, three):
        body = ask(three, {"all": True}).json()
        key = DownloadPackage.objects.get(pk=body["id"]).storage_key
        deletion.delete_project(three.owner, three.project)
        assert not DownloadPackage.objects.exists()
        with pytest.raises(privatefiles.StoredFileMissing):
            privatefiles.read_file(key)
