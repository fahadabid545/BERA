import io
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from core import middleware
from core.tests.factories import make_company, make_company_user, start_session_for
from cvs import storage
from cvs.file_checks import OLE_SIGNATURE
from cvs.models import CvFile
from plans import subscriptions as subs
from plans.models import Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project
from usage import service as usage

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def docx_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
        archive.writestr("[Content_Types].xml", "<Types/>")
    return buffer.getvalue()


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


def make_plan(cvs_per_month=100, cvs_per_project=50, name="Basic", price=10):
    return Plan.objects.create(
        name=name,
        status="active",
        price_usd=price,
        cvs_per_month=cvs_per_month,
        cvs_per_project=cvs_per_project,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=10000,
    )


@pytest.fixture
def company():
    company = make_company()
    now = timezone.now()
    subs.activate(
        company.pk, make_plan(), period_start=now, period_end=now + timezone.timedelta(days=30)
    )
    return company


@pytest.fixture
def signed_in(company):
    return sign_in(company)


@pytest.fixture
def client(signed_in):
    return signed_in[1]


@pytest.fixture
def project(company, signed_in):
    return Project.objects.create(
        company=company,
        title="Backend engineer",
        job_description="text",
        reading_model="m",
        prompt_version="p",
        created_by=signed_in[0],
    )


def url(project):
    return f"/api/company/projects/{project.pk}/cvs/"


def upload(client, project, *files):
    sent = [SimpleUploadedFile(name, data) for name, data in files]
    return client.post(url(project), {"files": sent}, format="multipart")


def results(response):
    return [(r["name"], r["status"], r["code"]) for r in response.json()["results"]]


def stored_files(root):
    return sorted(path for path in Path(root).rglob("*") if path.is_file())


class TestRules:
    def test_the_screen_can_read_what_is_allowed(self, client, project):
        assert client.get(url(project)).json() == {
            "allowed_types": ["pdf", "docx"],
            "max_file_size_mb": 10,
            "max_files_per_batch": 50,
        }


class TestAccepting:
    def test_pdf_and_docx_are_accepted_and_stay_waiting(self, company, client, project, settings):
        response = upload(client, project, ("a.pdf", PDF), ("b.docx", docx_bytes()))
        assert response.status_code == 200
        assert results(response) == [("a.pdf", "accepted", ""), ("b.docx", "accepted", "")]
        rows = CvFile.objects.filter(project=project)
        assert {row.status for row in rows} == {"waiting"}
        assert {row.file_type for row in rows} == {"pdf", "docx"}
        assert len(stored_files(settings.PRIVATE_FILES_ROOT)) == 2

    def test_the_stored_file_is_the_uploaded_one(self, client, project):
        upload(client, project, ("a.pdf", PDF))
        row = CvFile.objects.get(project=project)
        assert storage.read_file(row.storage_key) == PDF
        assert row.size_bytes == len(PDF)

    def test_each_accepted_file_is_counted_as_waiting_not_scored(self, company, client, project):
        upload(client, project, ("a.pdf", PDF), ("b.pdf", PDF))
        assert usage.waiting_cvs(company.pk) == 2
        assert usage.current_usage(company.pk)["cvs_scored"] == 0

    def test_the_file_belongs_to_the_projects_company_and_the_uploader(
        self, company, signed_in, client, project
    ):
        upload(client, project, ("a.pdf", PDF))
        row = CvFile.objects.get(project=project)
        assert (row.company_id, row.uploaded_by_id) == (company.pk, signed_in[0].pk)

    def test_a_member_may_upload(self, company, project):
        _, member = sign_in(company, role="member")
        assert results(upload(member, project, ("a.pdf", PDF))) == [("a.pdf", "accepted", "")]

    def test_a_file_name_can_never_choose_where_it_is_saved(self, client, project, settings):
        upload(client, project, ("../../evil.pdf", PDF))
        row = CvFile.objects.get(project=project)
        assert row.original_name == "evil.pdf"
        root = Path(settings.PRIVATE_FILES_ROOT).resolve()
        assert all(root in path.resolve().parents for path in stored_files(root))
        assert "evil" not in row.storage_key

    def test_the_type_is_not_case_sensitive(self, client, project):
        assert results(upload(client, project, ("CV.PDF", PDF)))[0][1] == "accepted"

    def test_nothing_chosen_is_a_form_mistake(self, client, project):
        response = client.post(url(project), {}, format="multipart")
        assert response.status_code == 400
        assert "files" in response.json()["error"]["fields"]


class TestEachProblemHasItsOwnMessageWhileGoodFilesContinue:
    def run(self, client, project, bad):
        response = upload(client, project, ("good.pdf", PDF), bad, ("also-good.docx", docx_bytes()))
        rows = response.json()["results"]
        assert [r["status"] for r in rows] == ["accepted", "rejected", "accepted"]
        assert CvFile.objects.filter(project=project).count() == 2
        return rows[1]

    def test_wrong_type(self, client, project):
        row = self.run(client, project, ("notes.txt", b"hello"))
        assert (row["code"], row["message"]) == (
            "wrong_type",
            "Only PDF or DOCX files can be uploaded.",
        )

    def test_no_extension(self, client, project):
        assert self.run(client, project, ("resume", PDF))["code"] == "wrong_type"

    def test_empty(self, client, project):
        row = self.run(client, project, ("empty.pdf", b""))
        assert (row["code"], row["message"]) == ("empty", "This file is empty.")

    def test_too_large(self, client, project):
        set_setting("uploads.max_file_size_mb", 1)
        row = self.run(client, project, ("big.pdf", PDF + b"0" * (1024 * 1024)))
        assert (row["code"], row["message"]) == ("too_large", "This file is larger than 1 MB.")

    def test_exactly_the_size_limit_is_allowed(self, client, project):
        set_setting("uploads.max_file_size_mb", 1)
        data = PDF + b"0" * (1024 * 1024 - len(PDF) - 5) + b"%%EOF"
        assert len(data) == 1024 * 1024
        assert results(upload(client, project, ("edge.pdf", data)))[0][1] == "accepted"

    def test_damaged_pdf(self, client, project):
        row = self.run(client, project, ("broken.pdf", b"not really a pdf"))
        assert (row["code"], row["message"]) == (
            "damaged",
            "This file looks damaged and could not be read.",
        )

    def test_a_cut_off_pdf_is_damaged(self, client, project):
        assert self.run(client, project, ("cut.pdf", PDF[:30]))["code"] == "damaged"

    def test_damaged_docx(self, client, project):
        assert self.run(client, project, ("broken.docx", b"not a zip"))["code"] == "damaged"

    def test_a_zip_that_is_not_a_word_file_is_damaged(self, client, project):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("other.txt", "x")
        assert self.run(client, project, ("odd.docx", buffer.getvalue()))["code"] == "damaged"

    def test_password_protected_pdf(self, client, project):
        data = PDF.replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 5 0 R")
        row = self.run(client, project, ("locked.pdf", data))
        assert (row["code"], row["message"]) == (
            "password_protected",
            "This file is password protected. Remove the password and upload it again.",
        )

    def test_password_protected_docx(self, client, project):
        row = self.run(client, project, ("locked.docx", OLE_SIGNATURE + b"\x00" * 100))
        assert row["code"] == "password_protected"

    def test_a_refused_file_leaves_nothing_behind(self, client, project, settings):
        upload(client, project, ("notes.txt", b"hello"), ("empty.pdf", b""))
        assert not CvFile.objects.exists()
        assert stored_files(settings.PRIVATE_FILES_ROOT) == []


class TestTooManyFiles:
    def test_files_past_the_batch_size_are_refused_and_the_rest_continue(self, client, project):
        set_setting("uploads.max_files_per_batch", 3)
        response = upload(client, project, *[(f"{n}.pdf", PDF) for n in range(5)])
        assert [r["status"] for r in response.json()["results"]] == ["accepted"] * 3 + [
            "rejected"
        ] * 2
        assert response.json()["results"][3]["code"] == "too_many_files"
        assert response.json()["results"][3]["message"] == "Only 3 files can be added at a time."
        assert CvFile.objects.count() == 3


class TestPlanLimits:
    def test_the_monthly_limit_stops_the_files_beyond_it_with_the_upgrade_prompt(
        self, company, client, project
    ):
        Plan.objects.update(cvs_per_month=2)
        make_plan(cvs_per_month=500, name="Bigger", price=99)
        response = upload(client, project, *[(f"{n}.pdf", PDF) for n in range(3)])
        rows = response.json()["results"]
        assert [r["status"] for r in rows] == ["accepted", "accepted", "rejected"]
        assert rows[2]["code"] == "monthly_cv_limit_reached"
        assert rows[2]["prompt"] == "upgrade"
        assert CvFile.objects.count() == 2

    def test_the_per_project_limit_applies_to_what_is_already_there(self, client, project):
        Plan.objects.update(cvs_per_project=3)
        upload(client, project, ("a.pdf", PDF), ("b.pdf", PDF))
        rows = upload(client, project, ("c.pdf", PDF), ("d.pdf", PDF)).json()["results"]
        assert [r["status"] for r in rows] == ["accepted", "rejected"]
        assert rows[1]["code"] == "project_cv_limit_reached"

    def test_another_project_has_its_own_project_limit(self, company, signed_in, client, project):
        Plan.objects.update(cvs_per_project=1)
        other = Project.objects.create(
            company=company,
            title="B",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=signed_in[0],
        )
        upload(client, project, ("a.pdf", PDF))
        assert results(upload(client, other, ("b.pdf", PDF)))[0][1] == "accepted"

    def test_an_ended_subscription_shows_the_renewal_prompt(self, company, client, project):
        subs.expire(company.pk)
        row = upload(client, project, ("a.pdf", PDF)).json()["results"][0]
        assert (row["status"], row["prompt"]) == ("rejected", "renewal")
        assert not CvFile.objects.exists()

    def test_refused_files_are_not_counted(self, company, client, project):
        Plan.objects.update(cvs_per_month=1)
        upload(client, project, ("notes.txt", b"x"), ("empty.pdf", b""))
        assert usage.waiting_cvs(company.pk) == 0
        assert results(upload(client, project, ("a.pdf", PDF)))[0][1] == "accepted"


class TestUploadRateLimit:
    def test_files_are_counted_one_by_one_against_the_allowance(self, client, project):
        set_setting("rate_limits.upload_files_per_10_minutes", 3)
        assert upload(client, project, ("a.pdf", PDF), ("b.pdf", PDF)).status_code == 200
        response = upload(client, project, ("c.pdf", PDF), ("d.pdf", PDF))
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "too_many_requests"
        assert CvFile.objects.count() == 2

    def test_the_allowance_belongs_to_the_company(self, company, client, project):
        set_setting("rate_limits.upload_files_per_10_minutes", 1)
        upload(client, project, ("a.pdf", PDF))
        other = make_company()
        now = timezone.now()
        subs.activate(
            other.pk,
            Plan.objects.first(),
            period_start=now,
            period_end=now + timezone.timedelta(days=30),
        )
        stranger, theirs = sign_in(other)
        their_project = Project.objects.create(
            company=other,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=stranger,
        )
        assert upload(theirs, their_project, ("a.pdf", PDF)).status_code == 200

    def test_the_default_is_100_files_per_10_minutes(self):
        from core.rate_limits import UPLOADS
        from platform_settings.service import get_setting

        assert (get_setting(UPLOADS.setting_key), UPLOADS.window_seconds) == (100, 600)


class TestAccess:
    def test_an_archived_project_takes_no_uploads(self, client, project):
        Project.objects.filter(pk=project.pk).update(status="archived")
        response = upload(client, project, ("a.pdf", PDF))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_archived"
        assert not CvFile.objects.exists()

    def test_nobody_signed_in_is_refused(self, project):
        response = APIClient().post(url(project), {}, format="multipart")
        assert response.status_code == 401

    def test_another_companys_project_is_not_found_and_nothing_is_saved(self, client, settings):
        stranger = make_company()
        theirs = Project.objects.create(
            company=stranger,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=make_company_user(stranger),
        )
        assert upload(client, theirs, ("a.pdf", PDF)).status_code == 404
        assert client.get(url(theirs)).status_code == 404
        assert not CvFile.objects.exists()
        assert stored_files(settings.PRIVATE_FILES_ROOT) == []

    def test_the_company_cannot_be_chosen_in_the_request(self, company, client, project):
        other = make_company()
        sent = SimpleUploadedFile("a.pdf", PDF)
        client.post(url(project), {"files": [sent], "company": str(other.pk)}, format="multipart")
        assert CvFile.objects.get().company_id == company.pk


class TestAnotherCompany:
    def test_a_file_always_belongs_to_the_projects_company(self, company, client, project):
        upload(client, project, ("a.pdf", PDF))
        assert CvFile.objects.get().company_id == company.pk

    def test_the_limit_counts_only_the_own_company(self, company, client, project):
        Plan.objects.update(cvs_per_month=1)
        other = make_company()
        now = timezone.now()
        subs.activate(
            other.pk,
            Plan.objects.first(),
            period_start=now,
            period_end=now + timezone.timedelta(days=30),
        )
        stranger, theirs = sign_in(other)
        their_project = Project.objects.create(
            company=other,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=stranger,
        )
        upload(theirs, their_project, ("a.pdf", PDF))
        assert results(upload(client, project, ("b.pdf", PDF)))[0][1] == "accepted"


class TestFailureCleanup:
    def test_if_saving_fails_part_way_nothing_stays_recorded_or_stored(
        self, company, client, project, settings, monkeypatch
    ):
        real_save = storage.save_file
        calls = []

        def flaky(key, data):
            calls.append(key)
            if len(calls) == 2:
                raise OSError("disk full")
            real_save(key, data)

        monkeypatch.setattr(storage, "save_file", flaky)
        client.raise_request_exception = False
        response = upload(client, project, ("a.pdf", PDF), ("b.pdf", PDF))
        assert response.status_code == 500
        assert "disk" not in response.content.decode()
        assert not CvFile.objects.exists()
        assert stored_files(settings.PRIVATE_FILES_ROOT) == []
        assert usage.waiting_cvs(company.pk) == 0


class TestDeletingTheProject:
    def test_the_files_are_removed_from_storage_and_usage_history_stays(
        self, company, signed_in, client, project, settings
    ):
        other = Project.objects.create(
            company=company,
            title="Other",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=signed_in[0],
        )
        upload(client, project, ("a.pdf", PDF), ("b.pdf", PDF))
        upload(client, other, ("c.pdf", PDF))
        response = client.delete(
            f"/api/company/projects/{project.pk}/", {"confirm_title": project.title}, format="json"
        )
        assert response.status_code == 204
        assert not CvFile.objects.filter(project_id=project.pk).exists()
        assert CvFile.objects.filter(project=other).count() == 1
        assert len(stored_files(settings.PRIVATE_FILES_ROOT)) == 1
        assert usage.waiting_cvs(company.pk) == 3


class TestRequestSize:
    def test_the_upload_route_allows_big_requests_other_routes_do_not(self):
        form = middleware.largest_allowed_request_bytes("/api/company/projects/")
        upload_size = middleware.largest_allowed_request_bytes("/api/company/projects/abc/cvs/")
        assert upload_size == 10 * 50 * 1024 * 1024
        assert upload_size > form
        assert middleware.largest_allowed_request_bytes("/api/company/projects/abc/") == form
        assert middleware.largest_allowed_request_bytes("/api/company/projects/abc/cvs/x/") == form


class TestStorage:
    def test_a_key_cannot_leave_the_storage_folder(self):
        with pytest.raises(ValueError):
            storage.save_file("../outside", b"x")

    def test_removing_a_missing_file_is_fine(self):
        storage.delete_file("cvs/none/none")
