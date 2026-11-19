import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone
from django_q.models import Schedule
from rest_framework.test import APIClient

import privatefiles
from activity.models import ActivityEntry
from audit.models import AuditEvent
from companies import deletion
from companies.invites import invite_member
from companies.models import Company, CompanyUser, Invitation
from core.models import CompanyOwnedModel
from core.tests.factories import make_company_user, start_session_for
from cvs import download_packages, retention
from cvs.models import Candidate, CandidateNote, CvFile, DownloadPackage, SharedReport
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add
from emailing.models import LinkToken, OutgoingEmail
from plans.models import Subscription
from projects.models import Project
from signin.models import Session
from signin.tests.models_for_tests import KINDS_OF_OBJECT
from usage.models import CvUsage

pytestmark = pytest.mark.django_db

URL = "/api/company/deletion/"
UNDO = "/api/auth/company/undo-deletion/"
LOGIN = "/api/auth/company/login/"
PASSWORD = "Fake-Passw0rd-123!"


@pytest.fixture(autouse=True)
def stand_in_tables(db):
    """The isolation tests register stand-in company models for the whole test run, and deleting a
    company looks at every model that points at it, so their tables must exist here too."""
    with connection.schema_editor() as editor:
        for model in KINDS_OF_OBJECT.values():
            editor.create_model(model)


@pytest.fixture
def tenant():
    made = Tenant(make_plan())
    made.company.name = "Fake Deletion Ltd"
    made.company.save()
    made.owner.email_verified = True
    made.owner.set_password(PASSWORD)
    made.owner.save()  # changing the password ends the owner's sessions, so sign in again
    issued = start_session_for(
        user_id=made.owner.pk, role="owner", company_id=made.company.pk, kind="company"
    )
    made.client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
    return made


def stored(tenant, name, score=70, **fields):
    row = add(tenant, name, score, **fields)
    privatefiles.save_file(row.storage_key, b"bytes")
    return row


def ask(tenant, **body):
    return tenant.client.post(
        URL, {"confirm_name": tenant.company.name, "acknowledge_subscription": True, **body},
        format="json",
    )  # fmt: skip


def mails(template):
    return list(OutgoingEmail.objects.filter(template=template))


def undo_token(mail):
    return mail.text_body.split("token=")[1].split()[0].strip()


def rows_of(company):
    """How many rows of every kind of company data the company still has."""
    return {
        model.__name__: model.objects.filter(company_id=company.pk).count()
        for model in apps.get_models()
        if issubclass(model, CompanyOwnedModel)
        and not model._meta.abstract
        and "tests" not in model.__module__
    }


def full_company(tenant):
    """A company with a bit of everything: CVs with files and notes, a second project, a shared
    report, zips, an invitation, a member, activity and usage."""
    first = stored(tenant, "a.pdf", 90, minutes=1)
    stored(tenant, "b.pdf", 80, minutes=2)
    CandidateNote.objects.create(
        company=tenant.company, candidate=first.candidate, author=tenant.owner, text="n"
    )
    other = Project.objects.create(
        company=tenant.company, title="Other", job_description="t", reading_model="m",
        created_by=tenant.owner,
    )  # fmt: skip
    keep = tenant.project
    tenant.project = other
    stored(tenant, "c.pdf", 70, minutes=3)
    tenant.project = keep
    tenant.client.post(f"/api/company/projects/{keep.pk}/reports/", {"days": 7}, format="json")
    tenant.client.post(f"/api/company/projects/{keep.pk}/downloads/", {"all": True}, format="json")
    tenant.client.post("/api/company/downloads/export/", {}, format="json")
    invite_member(tenant.owner, "invited@example.test")
    make_company_user(tenant.company, role="member")
    return tenant


class TestOverview:
    def test_it_says_the_subscription_is_active(self, tenant):
        shown = tenant.client.get(URL).json()
        assert shown["subscription"]["active"] is True
        assert shown["subscription"]["state"] == "active"

    def test_no_plan_is_not_an_active_subscription(self, tenant):
        Subscription.objects.filter(company=tenant.company).update(state="no_plan")
        assert tenant.client.get(URL).json()["subscription"]["active"] is False

    def test_a_member_may_not_see_it(self, tenant):
        member = make_company_user(tenant.company, role="member")
        issued = start_session_for(
            user_id=member.pk, role="member", company_id=tenant.company.pk, kind="company"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.get(URL).status_code == 403
        assert (
            client.post(URL, {"confirm_name": tenant.company.name}, format="json").status_code
            == 403
        )
        assert Company.objects.get().status == "active"

    def test_signed_out_is_refused(self):
        assert APIClient().get(URL).status_code == 401


class TestAsking:
    def test_the_name_must_be_typed_exactly(self, tenant):
        for wrong in ("", "fake deletion ltd", "Fake Deletion Ltd ", "Other"):
            response = ask(tenant, confirm_name=wrong)
            assert response.status_code == 400
            assert "confirm_name" in response.json()["error"]["fields"]
        assert Company.objects.get().status == "active"

    def test_an_active_subscription_must_be_acknowledged(self, tenant):
        response = tenant.client.post(URL, {"confirm_name": tenant.company.name}, format="json")
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "subscription_active"
        assert error["details"]["state"] == "active"
        assert Company.objects.get().status == "active"

    def test_a_company_without_a_subscription_needs_no_acknowledgement(self, tenant):
        Subscription.objects.filter(company=tenant.company).update(state="expired")
        response = tenant.client.post(URL, {"confirm_name": tenant.company.name}, format="json")
        assert response.status_code == 202

    def test_it_starts_a_grace_period_of_14_days(self, tenant):
        before = timezone.now()
        response = ask(tenant)
        assert response.status_code == 202
        company = Company.objects.get()
        assert company.status == "pending_deletion"
        assert company.deletion_requested_at >= before
        assert company.deletion_due_at - company.deletion_requested_at == timedelta(days=14)
        assert response.json()["due_at"] == company.deletion_due_at.isoformat()

    def test_the_grace_period_is_a_platform_setting(self, tenant):
        set_setting("account.deletion_grace_days", 3)
        ask(tenant)
        company = Company.objects.get()
        assert company.deletion_due_at - company.deletion_requested_at == timedelta(days=3)

    def test_nothing_is_removed_during_the_grace_period(self, tenant):
        full_company(tenant)
        before = rows_of(tenant.company)
        ask(tenant)
        deletion.remove_due_companies()
        assert rows_of(tenant.company) == before
        assert privatefiles.read_file(CvFile.objects.first().storage_key) == b"bytes"

    def test_everybody_is_signed_out_and_cannot_sign_in(self, tenant):
        member = make_company_user(tenant.company, role="member", email_verified=True)
        member.set_password(PASSWORD)
        member.save()
        ask(tenant)
        assert tenant.client.get(URL).status_code == 401
        for person in (tenant.owner, member):
            response = APIClient().post(
                LOGIN, {"email": person.email, "password": PASSWORD}, format="json"
            )
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "company_deletion_pending"

    def test_it_cannot_be_asked_for_twice(self, tenant):
        ask(tenant)
        with pytest.raises(deletion.AppError) as refused:
            deletion.request_deletion(
                CompanyUser.objects.get(pk=tenant.owner.pk),
                Company.objects.get(),
                "Fake Deletion Ltd",
                True,
            )
        assert refused.value.code == "company_not_active"

    def test_the_owner_gets_an_email_with_the_date_and_an_undo_link(self, tenant):
        ask(tenant)
        (mail,) = mails("deletion_scheduled")
        assert mail.to_address == tenant.owner.email
        assert "/undo-company-deletion?token=" in mail.text_body
        due = Company.objects.get().deletion_due_at
        assert f"{due.day} {due:%B %Y}" in mail.text_body
        assert "Fake Deletion" not in mail.text_body

    def test_it_is_audited_without_a_name_or_address(self, tenant):
        ask(tenant)
        event = AuditEvent.objects.get(kind="company.deletion_requested")
        assert event.company_id == tenant.company.pk
        text = str(event.__dict__)
        assert "Fake Deletion" not in text and tenant.owner.email not in text


class TestUndoing:
    def asked(self, tenant):
        ask(tenant)
        return undo_token(mails("deletion_scheduled")[0])

    def test_the_link_makes_the_company_active_again_without_signing_in(self, tenant):
        token = self.asked(tenant)
        response = APIClient().post(UNDO, {"token": token}, format="json")
        assert response.status_code == 200
        company = Company.objects.get()
        assert company.status == "active"
        assert (company.deletion_requested_at, company.deletion_due_at) == (None, None)
        login = APIClient().post(
            LOGIN, {"email": tenant.owner.email, "password": PASSWORD}, format="json"
        )
        assert login.status_code == 200

    def test_the_owner_is_told_and_it_is_audited(self, tenant):
        APIClient().post(UNDO, {"token": self.asked(tenant)}, format="json")
        assert any("will not be deleted" in mail.subject for mail in mails("account_notice"))
        event = AuditEvent.objects.get(kind="company.deletion_undone")
        assert event.company_id == tenant.company.pk

    def test_the_link_works_once(self, tenant):
        token = self.asked(tenant)
        APIClient().post(UNDO, {"token": token}, format="json")
        again = APIClient().post(UNDO, {"token": token}, format="json")
        assert again.status_code == 400
        assert again.json()["error"]["code"] == "link_used"

    def test_a_made_up_link_is_refused(self, tenant):
        self.asked(tenant)
        response = APIClient().post(UNDO, {"token": "not-a-real-token"}, format="json")
        assert response.status_code == 400
        assert Company.objects.get().status == "pending_deletion"

    def test_a_link_for_something_else_cannot_undo_it(self, tenant):
        from emailing.link_tokens import issue_link_token

        self.asked(tenant)
        other = issue_link_token(LinkToken.Purpose.VERIFY_EMAIL, tenant.owner.pk, 1)
        response = APIClient().post(UNDO, {"token": other}, format="json")
        assert response.status_code == 400
        assert Company.objects.get().status == "pending_deletion"

    def test_an_old_link_stops_working_when_the_grace_period_is_over(self, tenant):
        token = self.asked(tenant)
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        response = APIClient().post(UNDO, {"token": token}, format="json")
        assert response.json()["error"]["code"] == "link_expired"

    def test_after_the_removal_the_link_is_not_valid(self, tenant):
        token = self.asked(tenant)
        Company.objects.update(deletion_due_at=timezone.now() - timedelta(minutes=1))
        deletion.remove_due_companies()
        response = APIClient().post(UNDO, {"token": token}, format="json")
        assert response.status_code == 400

    def test_undoing_does_not_start_any_removal(self, tenant):
        full_company(tenant)
        before = rows_of(tenant.company)
        APIClient().post(UNDO, {"token": self.asked(tenant)}, format="json")
        Company.objects.update(deletion_due_at=timezone.now() - timedelta(days=1))
        deletion.remove_due_companies()
        assert rows_of(tenant.company) == before


class TestRemoval:
    def due(self, tenant):
        ask(tenant)
        Company.objects.filter(pk=tenant.company.pk).update(
            deletion_due_at=timezone.now() - timedelta(minutes=1)
        )

    def test_nothing_goes_before_the_grace_period_ends(self, tenant):
        full_company(tenant)
        ask(tenant)
        assert deletion.remove_due_companies() == 0
        assert Company.objects.filter(pk=tenant.company.pk).exists()

    def test_everything_of_the_company_goes_after_it(self, tenant):
        full_company(tenant)
        keys = [cv.storage_key for cv in CvFile.objects.all()]
        keys += [package.storage_key for package in DownloadPackage.objects.all()]
        assert len(keys) == 5
        company_id = tenant.company.pk
        self.due(tenant)
        assert deletion.remove_due_companies() == 1
        assert not Company.objects.filter(pk=company_id).exists()
        assert not CompanyUser.objects.filter(company_id=company_id).exists()
        assert not Invitation.objects.filter(company_id=company_id).exists()
        assert not Session.objects.filter(company_id=company_id).exists()
        assert not Project.objects.exists() and not Candidate.objects.exists()
        assert not SharedReport.objects.exists()
        assert not CvUsage.objects.filter(company_id=company_id).exists()
        for key in keys:
            with pytest.raises(privatefiles.StoredFileMissing):
                privatefiles.read_file(key)

    def test_every_kind_of_company_data_is_gone(self, tenant):
        full_company(tenant)
        company_id = tenant.company.pk
        self.due(tenant)
        deletion.remove_due_companies()
        for model in apps.get_models():
            if issubclass(model, CompanyOwnedModel) and not model._meta.abstract:
                if "tests" not in model.__module__:
                    assert not model.objects.filter(company_id=company_id).exists(), model

    def test_another_company_is_untouched(self, tenant):
        theirs = Tenant(make_plan())
        kept = stored(theirs, "theirs.pdf")
        before = rows_of(theirs.company)
        full_company(tenant)
        self.due(tenant)
        deletion.remove_due_companies()
        assert rows_of(theirs.company) == before
        assert privatefiles.read_file(kept.storage_key) == b"bytes"
        assert Company.objects.filter(pk=theirs.company.pk).exists()

    def test_the_audit_log_keeps_ids_and_kinds_only(self, tenant):
        full_company(tenant)
        self.due(tenant)
        deletion.remove_due_companies()
        event = AuditEvent.objects.get(kind="company.deleted")
        assert event.company_id == tenant.company.pk
        for entry in AuditEvent.objects.all():
            text = str(entry.__dict__)
            assert "Fake Deletion" not in text and tenant.owner.email not in text
            assert "a.pdf" not in text
        assert AuditEvent.objects.filter(kind="company.deletion_requested").exists()

    def test_the_activity_log_goes_with_the_company(self, tenant):
        full_company(tenant)
        assert ActivityEntry.objects.filter(company=tenant.company).exists()
        self.due(tenant)
        deletion.remove_due_companies()
        assert not ActivityEntry.objects.exists()

    def test_the_owner_is_told_it_is_done(self, tenant):
        self.due(tenant)
        deletion.remove_due_companies()
        assert any("was deleted" in mail.subject for mail in mails("account_notice"))
        assert "Fake Deletion" not in mails("account_notice")[-1].text_body

    def test_a_file_the_store_cannot_delete_stops_it_and_it_is_tried_again(
        self, tenant, monkeypatch
    ):
        full_company(tenant)
        self.due(tenant)
        before = rows_of(tenant.company)
        real = privatefiles.delete_file

        def unavailable(key):
            raise privatefiles.StorageUnavailable()

        monkeypatch.setattr("cvs.service.storage.delete_file", unavailable)
        assert deletion.remove_due_companies() == 0
        assert rows_of(tenant.company) == before
        assert Company.objects.get().status == "pending_deletion"
        monkeypatch.setattr("cvs.service.storage.delete_file", real)
        assert deletion.remove_due_companies() == 1
        assert not Company.objects.filter(pk=tenant.company.pk).exists()

    def test_one_company_that_fails_does_not_stop_the_next(self, tenant, monkeypatch):
        other = Tenant(make_plan())
        for made in (tenant, other):
            ask(made)
        Company.objects.update(deletion_due_at=timezone.now() - timedelta(minutes=1))
        real = deletion.remove_company

        def flaky(company_id):
            if company_id == tenant.company.pk:
                raise RuntimeError("boom")
            real(company_id)

        monkeypatch.setattr(deletion, "remove_company", flaky)
        assert deletion.remove_due_companies() == 1
        assert Company.objects.filter(pk=tenant.company.pk).exists()
        assert not Company.objects.filter(pk=other.company.pk).exists()

    def test_the_retention_job_leaves_a_company_being_deleted_alone_about_warnings(self, tenant):
        Company.objects.update(retention_days=30)
        row = stored(tenant, "a.pdf")
        CvFile.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=25))
        ask(tenant)
        assert retention.warn_company(tenant.company.pk) == 0
        assert not mails("retention_warning")

    def test_the_removal_is_scheduled_daily(self):
        job = Schedule.objects.get(func="companies.deletion.remove_due_companies")
        assert (job.schedule_type, job.repeats) == (Schedule.DAILY, -1)

    def test_it_works_in_a_worker_that_has_loaded_no_web_routes(self):
        script = (
            "import django, os;"
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
            "django.setup();"
            "from companies import deletion;"
            "deletion._load_registrations();"
            "from projects import deletion as registry;"
            "print(sorted(registry.DATA_REMOVERS), sorted(registry.WORK_STOPPERS))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parents[2],
        )
        assert result.returncode == 0, result.stderr[-500:]
        for name in ("CvFile", "Candidate", "SharedReport", "DownloadPackage", "Requirement"):
            assert name in result.stdout
        assert "CvProcessing" in result.stdout
        assert download_packages  # imported for the registration it makes
