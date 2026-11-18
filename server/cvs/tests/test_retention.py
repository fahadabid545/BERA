"""Retention of candidate data, with shortened periods so a few days stand for months."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from django_q.models import Schedule
from rest_framework.test import APIClient

import privatefiles
from activity.models import ActivityEntry
from audit.models import AuditEvent
from companies.models import Company
from core.tests.factories import make_company_user, start_session_for
from cvs import download_packages, retention
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
from emailing.models import OutgoingEmail
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project
from usage.models import CvUsage

pytestmark = pytest.mark.django_db

SETTINGS = "/api/company/settings/"
PREVIEW = "/api/company/settings/retention-preview/"


@pytest.fixture
def tenant():
    made = Tenant(make_plan())
    made.company.retention_days = 30
    made.company.save()
    PlatformSetting.objects.create(key="retention.choices_days", value=[7, 30, 90, 180])
    clear_cache()
    return made


def aged(tenant, name, age_days, score=70, **fields):
    """A CV uploaded `age_days` ago, with its stored file."""
    row = add(tenant, name, score, **fields)
    CvFile.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=age_days))
    privatefiles.save_file(row.storage_key, b"bytes")
    row.refresh_from_db()
    return row


def mails(template):
    return [mail for mail in OutgoingEmail.objects.filter(template=template)]


class TestDeletion:
    def test_a_cv_past_the_period_goes_with_everything_of_it(self, tenant):
        old = aged(tenant, "old.pdf", 31)
        CandidateNote.objects.create(
            company=tenant.company, candidate=old.candidate, author=tenant.owner, text="note"
        )
        key = old.storage_key
        retention.purge_company(tenant.company.pk)
        assert not CvFile.objects.filter(pk=old.pk).exists()
        for model in (CvProfile, CvContact, Candidate, CandidateScore, CandidateNote):
            assert not model.objects.filter(company=tenant.company).exists(), model
        with pytest.raises(privatefiles.StoredFileMissing):
            privatefiles.read_file(key)

    def test_a_cv_inside_the_period_stays(self, tenant):
        young = aged(tenant, "young.pdf", 29)
        retention.purge_company(tenant.company.pk)
        assert CvFile.objects.filter(pk=young.pk).exists()
        assert privatefiles.read_file(young.storage_key) == b"bytes"

    def test_the_period_is_counted_from_the_upload(self, tenant):
        edge = aged(tenant, "edge.pdf", 30)
        CvFile.objects.filter(pk=edge.pk).update(created_at=timezone.now() - timedelta(days=29))
        retention.purge_company(tenant.company.pk)
        assert CvFile.objects.filter(pk=edge.pk).exists()

    def test_each_company_follows_its_own_choice(self, tenant):
        other = Tenant(make_plan())  # no choice: the platform default of 180 days
        mine = aged(tenant, "mine.pdf", 100)
        theirs = aged(other, "theirs.pdf", 100)
        retention.run_retention()
        assert not CvFile.objects.filter(pk=mine.pk).exists()
        assert CvFile.objects.filter(pk=theirs.pk).exists()

    def test_the_platform_default_applies_when_no_choice_was_made(self, tenant):
        Company.objects.filter(pk=tenant.company.pk).update(retention_days=None)
        PlatformSetting.objects.create(key="retention.default_days", value=7)
        clear_cache()
        row = aged(tenant, "a.pdf", 8)
        retention.purge_company(tenant.company.pk)
        assert not CvFile.objects.filter(pk=row.pk).exists()

    def test_cvs_still_being_processed_are_never_deleted(self, tenant):
        waiting = aged(tenant, "waiting.pdf", 400, None, status="waiting")
        reading = aged(tenant, "reading.pdf", 400, None, status="reading")
        retention.purge_company(tenant.company.pk)
        assert CvFile.objects.filter(pk__in=[waiting.pk, reading.pk]).count() == 2

    def test_failed_and_cancelled_cvs_are_deleted_too(self, tenant):
        failed = aged(tenant, "failed.pdf", 40, None, status="failed")
        cancelled = aged(tenant, "cancelled.pdf", 40, None, status="cancelled")
        retention.purge_company(tenant.company.pk)
        assert not CvFile.objects.filter(pk__in=[failed.pk, cancelled.pk]).exists()

    def test_another_companys_data_is_never_touched(self, tenant):
        other = Tenant(make_plan())
        theirs = aged(other, "theirs.pdf", 400)
        retention.purge_company(tenant.company.pk)
        assert CvFile.objects.filter(pk=theirs.pk).exists()

    def test_the_project_its_requirements_and_the_usage_history_stay(self, tenant):
        aged(tenant, "old.pdf", 40)
        counted = CvUsage.objects.count()
        retention.purge_company(tenant.company.pk)
        assert Project.objects.filter(pk=tenant.project.pk).exists()
        assert CvUsage.objects.count() == counted

    def test_a_file_the_store_cannot_delete_is_left_whole_and_tried_again(
        self, tenant, monkeypatch
    ):
        old = aged(tenant, "old.pdf", 40)
        real = privatefiles.delete_file

        def unavailable(key):
            raise privatefiles.StorageUnavailable()

        monkeypatch.setattr("cvs.service.storage.delete_file", unavailable)
        assert retention.purge_company(tenant.company.pk) == {"cvs": 0, "shared_links": 0}
        assert CvFile.objects.filter(pk=old.pk).exists()
        assert not ActivityEntry.objects.filter(kind="data_expired").exists()
        monkeypatch.setattr("cvs.service.storage.delete_file", real)
        assert retention.purge_company(tenant.company.pk)["cvs"] == 1
        assert not CvFile.objects.filter(pk=old.pk).exists()

    def test_a_zip_holding_a_deleted_cv_is_deleted_too(self, tenant):
        old = aged(tenant, "old.pdf", 40)
        young = aged(tenant, "young.pdf", 1)
        asker = SimpleNamespace(user_id=tenant.owner.pk)
        package = download_packages.request_package(tenant.project, asker)
        other = download_packages.request_package(tenant.project, asker, [str(young.candidate.pk)])
        key = package.storage_key
        retention.purge_company(tenant.company.pk)
        assert not DownloadPackage.objects.filter(pk=package.pk).exists()
        assert DownloadPackage.objects.filter(pk=other.pk).exists()
        with pytest.raises(privatefiles.StoredFileMissing):
            privatefiles.read_file(key)
        assert old.pk


class TestTheLog:
    def test_a_deletion_is_logged_with_counts_and_no_person(self, tenant):
        aged(tenant, "secret-name.pdf", 40)
        aged(tenant, "other.pdf", 41)
        retention.purge_company(tenant.company.pk)
        entry = ActivityEntry.objects.get(company=tenant.company, kind="data_expired")
        assert entry.details == {"files": 2, "shared_links": 0}
        assert entry.actor_id is None and entry.actor_name == ""
        assert "secret-name" not in str(entry.__dict__)

    def test_nothing_deleted_logs_nothing(self, tenant):
        aged(tenant, "young.pdf", 1)
        retention.purge_company(tenant.company.pk)
        assert not ActivityEntry.objects.filter(kind="data_expired").exists()


def share(tenant):
    response = tenant.client.post(
        f"/api/company/projects/{tenant.project.pk}/reports/", {"days": 7}, format="json"
    )
    assert response.status_code == 201
    return response.json()["token"]


def public(token):
    return APIClient().get(f"/api/reports/{token}/")


class TestShareLinks:
    def test_a_link_stops_working_when_its_oldest_cv_is_deleted(self, tenant):
        old = aged(tenant, "old.pdf", 29, 90)
        aged(tenant, "young.pdf", 1, 80)
        token = share(tenant)
        assert public(token).status_code == 200
        CvFile.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
        SharedReport.objects.update(data_from=timezone.now() - timedelta(days=31))
        result = retention.purge_company(tenant.company.pk)
        assert result == {"cvs": 1, "shared_links": 1}
        gone = public(token)
        assert gone.status_code == 404
        assert gone.json() == public("not-a-real-token").json()
        assert not SharedReport.objects.exists()

    def test_a_link_whose_data_is_all_inside_the_period_keeps_working(self, tenant):
        aged(tenant, "young.pdf", 5, 90)
        token = share(tenant)
        retention.purge_company(tenant.company.pk)
        assert public(token).status_code == 200

    def test_a_report_made_before_the_age_was_kept_goes_by_its_own_age(self, tenant):
        aged(tenant, "young.pdf", 5, 90)
        token = share(tenant)
        SharedReport.objects.update(data_from=None, created_at=timezone.now() - timedelta(days=45))
        retention.purge_company(tenant.company.pk)
        assert public(token).status_code == 404

    def test_the_report_records_the_upload_time_of_its_oldest_cv(self, tenant):
        old = aged(tenant, "old.pdf", 20, 90)
        aged(tenant, "young.pdf", 1, 80)
        share(tenant)
        assert SharedReport.objects.get().data_from == old.created_at


class TestWarning:
    def test_the_owner_is_told_once_a_week_before(self, tenant):
        aged(tenant, "soon.pdf", 25)  # 5 days left of 30
        aged(tenant, "later.pdf", 10)
        assert retention.warn_company(tenant.company.pk) == 1
        sent = mails("retention_warning")
        assert len(sent) == 1
        assert sent[0].to_address == tenant.owner.email
        assert "1 CV " in sent[0].text_body
        assert retention.warn_company(tenant.company.pk) == 0
        assert len(mails("retention_warning")) == 1

    def test_the_email_names_no_candidate_and_no_file(self, tenant):
        aged(tenant, "private-file-name.pdf", 25, who="Jane Example")
        retention.warn_company(tenant.company.pk)
        body = mails("retention_warning")[0]
        text = body.subject + body.text_body + body.html_body
        assert "private-file-name" not in text and "Jane" not in text

    def test_the_warning_time_is_a_platform_setting(self, tenant):
        aged(tenant, "a.pdf", 15)
        assert retention.warn_company(tenant.company.pk) == 0
        PlatformSetting.objects.create(key="retention.warning_days", value=20)
        clear_cache()
        assert retention.warn_company(tenant.company.pk) == 1

    def test_only_owners_are_told(self, tenant):
        member = make_company_user(tenant.company, role="member")
        aged(tenant, "a.pdf", 25)
        retention.warn_company(tenant.company.pk)
        assert [mail.to_address for mail in mails("retention_warning")] == [tenant.owner.email]
        assert member.email != tenant.owner.email

    def test_each_batch_is_warned_about_once_as_it_comes_near(self, tenant):
        first = aged(tenant, "a.pdf", 25)
        retention.warn_company(tenant.company.pk)
        second = aged(tenant, "b.pdf", 26)
        assert retention.warn_company(tenant.company.pk) == 1
        assert len(mails("retention_warning")) == 2
        assert CvFile.objects.get(pk=first.pk).expiry_warned_at is not None
        assert CvFile.objects.get(pk=second.pk).expiry_warned_at is not None

    def test_cvs_already_past_the_period_get_no_warning(self, tenant):
        aged(tenant, "late.pdf", 40)
        assert retention.warn_company(tenant.company.pk) == 0

    def test_cvs_still_being_processed_are_not_warned_about(self, tenant):
        aged(tenant, "wait.pdf", 25, None, status="waiting")
        assert retention.warn_company(tenant.company.pk) == 0

    def test_the_warning_says_how_many_and_when(self, tenant):
        aged(tenant, "a.pdf", 25)
        aged(tenant, "b.pdf", 26)
        retention.warn_company(tenant.company.pk)
        assert "2 CVs" in mails("retention_warning")[0].text_body


class TestTheDailyJob:
    def test_it_deletes_warns_and_clears_old_activity(self, tenant):
        old = aged(tenant, "old.pdf", 40)
        aged(tenant, "soon.pdf", 25)
        stale = ActivityEntry.objects.create(
            company=tenant.company, kind="download", details={}, actor_id=None
        )
        ActivityEntry.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        assert retention.run_retention() == 1
        assert not CvFile.objects.filter(pk=old.pk).exists()
        assert len(mails("retention_warning")) == 1
        assert not ActivityEntry.objects.filter(pk=stale.pk).exists()

    def test_running_it_twice_changes_nothing_more(self, tenant):
        aged(tenant, "old.pdf", 40)
        retention.run_retention()
        assert retention.run_retention() == 0

    def test_it_is_scheduled_daily(self):
        job = Schedule.objects.get(func="cvs.retention.run_retention")
        assert (job.schedule_type, job.repeats) == (Schedule.DAILY, -1)


def sign_in(company, role):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


class TestShorteningNeedsConfirmation:
    def test_the_preview_says_what_a_period_would_delete(self, tenant):
        aged(tenant, "a.pdf", 10)
        aged(tenant, "b.pdf", 40)
        response = tenant.client.get(PREVIEW, {"days": 7})
        assert response.status_code == 200
        assert response.json() == {"cvs": 2, "projects": 1, "shared_links": 0}
        assert tenant.client.get(PREVIEW, {"days": 90}).json()["cvs"] == 0

    def test_the_preview_counts_links_that_would_go(self, tenant):
        aged(tenant, "a.pdf", 20, 90)
        share(tenant)
        assert tenant.client.get(PREVIEW, {"days": 7}).json()["shared_links"] == 1

    def test_a_shorter_period_that_deletes_data_is_refused_until_confirmed(self, tenant):
        aged(tenant, "a.pdf", 10)
        response = tenant.client.patch(SETTINGS, {"retention_days": 7}, format="json")
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "retention_confirmation_needed"
        assert error["details"] == {"cvs": 1, "projects": 1, "shared_links": 0}
        tenant.company.refresh_from_db()
        assert tenant.company.retention_days == 30

    def test_once_confirmed_it_is_saved_and_logged_and_nothing_is_deleted_yet(self, tenant):
        old = aged(tenant, "a.pdf", 10)
        response = tenant.client.patch(
            SETTINGS, {"retention_days": 7, "acknowledge_deletion": True}, format="json"
        )
        assert response.status_code == 200
        tenant.company.refresh_from_db()
        assert tenant.company.retention_days == 7
        event = AuditEvent.objects.get(kind="retention.changed")
        assert event.details == {"from_days": 30, "to_days": 7}
        assert CvFile.objects.filter(pk=old.pk).exists()  # the daily job deletes it
        retention.run_retention()
        assert not CvFile.objects.filter(pk=old.pk).exists()

    def test_a_shorter_period_that_deletes_nothing_needs_no_confirmation(self, tenant):
        aged(tenant, "a.pdf", 3)
        response = tenant.client.patch(SETTINGS, {"retention_days": 7}, format="json")
        assert response.status_code == 200

    def test_a_longer_period_needs_no_confirmation(self, tenant):
        aged(tenant, "a.pdf", 40)
        response = tenant.client.patch(SETTINGS, {"retention_days": 90}, format="json")
        assert response.status_code == 200
        assert AuditEvent.objects.filter(kind="retention.changed").count() == 1

    def test_going_back_to_the_platform_default_counts_as_the_default_period(self, tenant):
        aged(tenant, "a.pdf", 40)
        response = tenant.client.patch(SETTINGS, {"retention_days": None}, format="json")
        assert response.status_code == 200  # 180 days is longer than 30

    def test_confirming_alone_is_not_a_change(self, tenant):
        response = tenant.client.patch(SETTINGS, {"acknowledge_deletion": True}, format="json")
        assert response.status_code == 400

    def test_changing_the_period_starts_the_warnings_over(self, tenant):
        aged(tenant, "a.pdf", 25)
        retention.warn_company(tenant.company.pk)
        tenant.client.patch(SETTINGS, {"retention_days": 90}, format="json")
        assert CvFile.objects.get().expiry_warned_at is None

    def test_a_period_that_is_not_offered_is_refused(self, tenant):
        assert tenant.client.get(PREVIEW, {"days": 45}).status_code == 400
        assert tenant.client.get(PREVIEW).status_code == 400


class TestOwnerOnly:
    def test_a_member_cannot_preview_or_change(self, tenant):
        member = sign_in(tenant.company, "member")
        assert member.get(PREVIEW, {"days": 7}).status_code == 403
        assert member.patch(SETTINGS, {"retention_days": 7}, format="json").status_code == 403

    def test_signed_out_is_refused(self):
        assert APIClient().get(PREVIEW, {"days": 7}).status_code == 401

    def test_the_preview_counts_only_the_own_company(self, tenant):
        other = Tenant(make_plan())
        aged(other, "theirs.pdf", 400)
        assert tenant.client.get(PREVIEW, {"days": 7}).json() == {
            "cvs": 0,
            "projects": 0,
            "shared_links": 0,
        }
