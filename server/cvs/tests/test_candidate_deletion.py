from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

import privatefiles
from activity.models import ActivityEntry
from audit.models import AuditEvent
from core.tests.factories import make_company_user, start_session_for
from cvs import download_packages
from cvs.models import (
    Candidate,
    CandidateNote,
    CandidateScore,
    CvContact,
    CvFile,
    CvProfile,
    DownloadPackage,
    SharedReport,
)
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add
from usage.models import CvUsage

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def stored(tenant, name, score=70, **fields):
    row = add(tenant, name, score, **fields)
    privatefiles.save_file(row.storage_key, b"bytes")
    return row


def url(tenant, row):
    return f"/api/company/projects/{tenant.project.pk}/candidates/{row.candidate.pk}/"


def sign_in(company, role="member"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


class TestDeleting:
    def test_the_owner_deletes_a_candidate_with_everything_of_theirs(self, tenant):
        row = stored(tenant, "a.pdf")
        key = row.storage_key
        CandidateNote.objects.create(
            company=tenant.company, candidate=row.candidate, author=tenant.owner, text="n"
        )
        response = tenant.client.delete(url(tenant, row))
        assert response.status_code == 204
        for model in (CvFile, CvProfile, CvContact, Candidate, CandidateScore, CandidateNote):
            assert not model.objects.filter(company=tenant.company).exists(), model
        with pytest.raises(privatefiles.StoredFileMissing):
            privatefiles.read_file(key)

    def test_a_member_may_delete_too(self, tenant):
        row = stored(tenant, "a.pdf")
        _, member = sign_in(tenant.company)
        assert member.delete(url(tenant, row)).status_code == 204
        assert not Candidate.objects.exists()

    def test_other_candidates_stay(self, tenant):
        gone = stored(tenant, "a.pdf", minutes=1)
        kept = stored(tenant, "b.pdf", minutes=2)
        tenant.client.delete(url(tenant, gone))
        assert Candidate.objects.get().pk == kept.candidate.pk
        assert privatefiles.read_file(kept.storage_key) == b"bytes"

    def test_it_can_be_done_at_any_time_even_in_an_archived_project(self, tenant):
        row = stored(tenant, "a.pdf")
        tenant.project.status = "archived"
        tenant.project.save()
        assert tenant.client.delete(url(tenant, row)).status_code == 204

    def test_the_usage_history_stays(self, tenant):
        row = stored(tenant, "a.pdf")
        counted = CvUsage.objects.count()
        tenant.client.delete(url(tenant, row))
        assert CvUsage.objects.count() == counted

    def test_deleting_twice_says_not_found(self, tenant):
        row = stored(tenant, "a.pdf")
        address = url(tenant, row)
        tenant.client.delete(address)
        assert tenant.client.delete(address).status_code == 404

    def test_a_cv_still_being_scored_cannot_be_deleted_yet(self, tenant):
        row = stored(tenant, "a.pdf", status="scoring")
        response = tenant.client.delete(url(tenant, row))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "candidate_processing"
        assert Candidate.objects.exists()

    def test_a_file_the_store_cannot_delete_leaves_everything_whole(self, tenant, monkeypatch):
        row = stored(tenant, "a.pdf")

        def unavailable(key):
            raise privatefiles.StorageUnavailable()

        monkeypatch.setattr("cvs.service.storage.delete_file", unavailable)
        assert tenant.client.delete(url(tenant, row)).status_code == 503
        assert Candidate.objects.exists() and CvFile.objects.exists()
        assert not ActivityEntry.objects.filter(kind="candidate_deleted").exists()


class TestCopiesOfTheirData:
    def test_a_zip_holding_the_cv_is_deleted_and_other_zips_stay(self, tenant):
        gone = stored(tenant, "a.pdf", minutes=1)
        kept = stored(tenant, "b.pdf", minutes=2)
        asker = SimpleNamespace(user_id=tenant.owner.pk)
        both = download_packages.request_package(tenant.project, asker)
        only_kept = download_packages.request_package(
            tenant.project, asker, [str(kept.candidate.pk)]
        )
        tenant.client.delete(url(tenant, gone))
        assert not DownloadPackage.objects.filter(pk=both.pk).exists()
        assert DownloadPackage.objects.filter(pk=only_kept.pk).exists()

    def test_a_shared_report_made_with_the_candidate_stops_working(self, tenant):
        gone = stored(tenant, "a.pdf", 90, minutes=1)
        stored(tenant, "b.pdf", 80, minutes=2)
        made = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/reports/", {"days": 7}, format="json"
        )
        token = made.json()["token"]
        assert APIClient().get(f"/api/reports/{token}/").status_code == 200
        tenant.client.delete(url(tenant, gone))
        assert APIClient().get(f"/api/reports/{token}/").status_code == 404
        assert not SharedReport.objects.exists()

    def test_a_report_without_this_candidate_stays(self, tenant):
        stored(tenant, "a.pdf", 90, minutes=1)
        other = stored(tenant, "b.pdf", 10, minutes=2)
        made = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/reports/", {"days": 7}, format="json"
        )
        report = SharedReport.objects.get()
        SharedReport.objects.filter(pk=report.pk).update(cv_ids=["not-this-one"])
        tenant.client.delete(url(tenant, other))
        assert made.status_code == 201 and SharedReport.objects.filter(pk=report.pk).exists()

    def test_a_report_made_before_the_cvs_were_recorded_goes_too(self, tenant):
        gone = stored(tenant, "a.pdf", 90)
        tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/reports/", {"days": 7}, format="json"
        )
        SharedReport.objects.update(cv_ids=[])
        tenant.client.delete(url(tenant, gone))
        assert not SharedReport.objects.exists()

    def test_the_report_records_its_cvs(self, tenant):
        first = stored(tenant, "a.pdf", 90)
        tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/reports/", {"days": 7}, format="json"
        )
        assert SharedReport.objects.get().cv_ids == [str(first.pk)]


class TestTheRecord:
    def test_the_deletion_is_logged_and_audited_without_a_person(self, tenant):
        row = stored(tenant, "secret-file-name.pdf")
        tenant.client.delete(url(tenant, row))
        entry = ActivityEntry.objects.get(kind="candidate_deleted")
        assert (entry.target_kind, entry.target_id) == ("project", str(tenant.project.pk))
        assert entry.details == {}
        event = AuditEvent.objects.get(kind="candidate.deleted")
        assert event.details == {"project_id": str(tenant.project.pk)}
        assert event.company_id == tenant.company.pk
        for text in (str(entry.__dict__), str(event.__dict__)):
            assert "secret-file-name" not in text and "Jane" not in text


class TestWhoMayDelete:
    def test_another_companys_candidate_is_not_found(self, tenant):
        other = Tenant(make_plan())
        theirs = stored(other, "theirs.pdf")
        response = tenant.client.delete(
            f"/api/company/projects/{tenant.project.pk}/candidates/{theirs.candidate.pk}/"
        )
        assert response.status_code == 404
        assert Candidate.objects.filter(pk=theirs.candidate.pk).exists()

    def test_a_candidate_of_another_project_is_not_found_under_this_one(self, tenant):
        row = stored(tenant, "a.pdf")
        wrong = f"/api/company/projects/{other_project(tenant).pk}/candidates/{row.candidate.pk}/"
        assert tenant.client.delete(wrong).status_code == 404
        assert Candidate.objects.exists()

    def test_signed_out_is_refused(self, tenant):
        row = stored(tenant, "a.pdf")
        assert APIClient().delete(url(tenant, row)).status_code == 401


def other_project(tenant):
    from projects.models import Project

    return Project.objects.create(
        company=tenant.company,
        title="Other",
        job_description="t",
        reading_model="m",
        created_by=tenant.owner,
    )
