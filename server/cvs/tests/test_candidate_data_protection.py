"""Candidate data is sensitive everywhere: encrypted at rest, masked where full detail is not
needed, never in logs, emails or admin views, and closed to admin and support staff."""

import ast
import importlib
import json
import logging
import pathlib

import pytest
from django.core import mail, serializers
from django.db import connection
from django.test import RequestFactory
from rest_framework.test import APIClient

from ai import client
from ai.client import AiAnswer
from core import logging_setup
from core.errors import AppError
from core.field_protection import decrypt_text
from core.personal_data import (
    CandidateDataOnly,
    mask_address,
    mask_contact,
    mask_email,
    mask_name,
    mask_phone,
)
from core.tests.factories import make_admin_user, make_company
from core.tests.test_route_protection import all_routes, authenticators_of
from cvs import candidates, processing, support_figures
from cvs.models import Candidate, CvContact, CvFile, CvProfile
from cvs.tests.test_candidate_record import make_cv
from signin import service
from signin.authentication import AdminAuthentication
from signin.company_views import CandidateDataView

pytestmark = pytest.mark.django_db

NAME = "Zelda Quillfeather"
EMAIL = "zelda.quillfeather@sentinel.example"
PHONE = "+1 555 010 7788"
ADDRESS = "99 Sentinel Road, Quillville"
CV_TEXT = (
    f"{NAME}\n{EMAIL} {PHONE}\n{ADDRESS}\n"
    "Senior Backend Engineer, 2018 - present. Wrote the Quillfeather zephyr scheduler in Python."
)
ANSWER = {
    "contact": {"name": NAME, "email": EMAIL, "phone": PHONE, "address": ADDRESS},
    "skills": ["Python"],
    "jobs": [{"title": "Senior Backend Engineer", "start": "2018", "end": "present"}],
    "education": [],
    "certifications": [],
    "languages": [],
    "summary": "A backend engineer.",
}
SENTINELS = (NAME, "Quillfeather", EMAIL, "7788", "Sentinel Road", "Quillville", "zephyr")


def assert_clean(text):
    """No candidate content (contact details or CV text) anywhere in the text."""
    lowered = text.lower()
    for sentinel in SENTINELS:
        assert sentinel.lower() not in lowered, f"{sentinel!r} found"


def admin_client(role="super"):
    admin = make_admin_user(role=role)
    issued = service.start_session(user_id=admin.pk, role=role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def stub_ai(monkeypatch):
    monkeypatch.setattr(client, "_send", lambda **call: AiAnswer(json.dumps(ANSWER), 10, 5))


@pytest.fixture
def real_pipeline():
    real = dict(processing.STEPS)
    processing.STEPS["text_reading"] = lambda context: context.state.update(text=CV_TEXT)
    yield
    processing.STEPS.clear()
    processing.STEPS.update(real)


def run_pipeline(row):
    row.claim_token = "11111111-1111-1111-1111-111111111111"
    row.save()
    processing.run_item(CvFile.objects.get(pk=row.pk))
    return CvFile.objects.get(pk=row.pk)


@pytest.fixture
def stored(stub_ai, real_pipeline):
    """A CV read all the way to a candidate, holding the sentinel details."""
    row = make_cv()
    run_pipeline(row)
    return CvFile.objects.get(pk=row.pk)


class TestContactDetailsAreEncryptedAtRest:
    def raw_row(self, cv):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name, email, phone, address FROM cvs_cvcontact WHERE cv_file_id = %s",
                [str(cv.pk)],
            )
            return cursor.fetchone()

    def test_the_database_holds_no_plain_contact_detail(self, stored):
        raw = self.raw_row(stored)
        assert all(raw)
        assert_clean(" ".join(raw))

    def test_the_application_reads_them_back(self, stored):
        contact = CvContact.objects.get(cv_file=stored)
        assert (contact.name, contact.email) == (NAME, EMAIL)
        assert (contact.phone, contact.address) == (PHONE, ADDRESS)

    def test_a_value_moved_to_another_column_cannot_be_opened(self, stored):
        raw_name, raw_email, _, _ = self.raw_row(stored)
        with pytest.raises(AppError):
            decrypt_text(raw_name, "cv_contact.email")
        assert decrypt_text(raw_email, "cv_contact.email") == EMAIL

    def test_an_empty_detail_is_stored_encrypted_too(self):
        cv = make_cv()
        CvProfile.objects.create(
            company_id=cv.company_id, cv_file=cv, content={}, model="m", prompt_version="p"
        )
        CvContact.objects.create(company_id=cv.company_id, cv_file=cv)
        assert all(self.raw_row(cv))
        assert CvContact.objects.get(cv_file=cv).phone == ""

    def test_the_migration_encrypts_rows_that_were_stored_as_plain_text(self):
        migration = importlib.import_module("cvs.migrations.0008_encrypt_contact_details")
        cv = make_cv()
        contact = CvContact.objects.create(company_id=cv.company_id, cv_file=cv, name="x")
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE cvs_cvcontact SET name = %s, email = %s, phone = %s, address = %s "
                "WHERE id = %s",
                [NAME, EMAIL, PHONE, "", contact.pk],
            )

        class SchemaEditor:
            pass

        editor = SchemaEditor()
        editor.connection = connection
        migration.encrypt_existing_rows(None, editor)
        assert all(self.raw_row(cv))
        assert_clean(" ".join(self.raw_row(cv)))
        reloaded = CvContact.objects.get(pk=contact.pk)
        assert (reloaded.name, reloaded.email, reloaded.phone) == (NAME, EMAIL, PHONE)
        assert reloaded.address == ""
        migration.decrypt_existing_rows(None, editor)
        assert self.raw_row(cv)[1] == EMAIL


class TestMasking:
    def test_email(self):
        assert mask_email("jane@example.com") == "j***@example.com"
        assert mask_email("") == "" and mask_email("not an email") == "***"

    def test_phone_keeps_only_the_last_four_digits(self):
        assert mask_phone("+1 (555) 010-2030") == "*******2030"
        assert mask_phone("1234") == "****" and mask_phone("") == ""

    def test_name_is_initials(self):
        assert mask_name("jane example") == "J. E." and mask_name("") == ""

    def test_address_is_never_shown_in_part(self):
        assert mask_address(ADDRESS) == "***" and mask_address("  ") == ""

    def test_a_contact_is_masked_whole_and_shows_nothing_of_the_originals(self, stored):
        masked = mask_contact(CvContact.objects.get(cv_file=stored))
        assert set(masked) == {"name", "email", "phone", "address"}
        assert masked["phone"] == "*******7788" and masked["address"] == "***"
        assert masked["name"] == "Z. Q." and masked["email"] == "z***@sentinel.example"
        assert_clean(json.dumps({**masked, "phone": ""}).replace("sentinel.example", ""))
        assert mask_contact({"email": EMAIL})["email"] == mask_email(EMAIL)


class TestAccessIsBlockedForAdminAndSupport:
    def ask(self, kind, role):
        request = RequestFactory().get("/")
        request.user = service.SignedInUser(
            user_id=1,
            role=role,
            company_id=None if kind == "admin" else 1,
            kind=kind,
            session_id="s",
        )
        return CandidateDataOnly().has_permission(request, None)

    @pytest.mark.parametrize("role", ["super", "support"])
    def test_admin_and_support_are_refused_with_a_clear_code(self, role):
        with pytest.raises(AppError) as refused:
            self.ask("admin", role)
        assert refused.value.code == "candidate_data_blocked"
        assert refused.value.status_code == 403

    @pytest.mark.parametrize("role", ["owner", "member"])
    def test_company_members_pass_the_check(self, role):
        assert self.ask("company", role) is True

    def test_every_view_with_candidate_content_uses_the_blocking_base(self):
        from cvs import views

        for name in ("ProjectCvUpload", "ProjectProcessing", "CancelUnstarted", "RetryFailedCv"):
            assert issubclass(getattr(views, name), CandidateDataView), name

    def test_an_admin_sign_in_cannot_use_any_candidate_route(self, stored):
        client_for_admin = admin_client("super")
        project_id = stored.project_id
        for route, view in all_routes():
            if not issubclass(view.cls, CandidateDataView):
                continue
            path = "/" + route.replace("<str:id>", str(project_id)).replace(
                "<str:cv_id>", str(stored.pk)
            )
            for method in ("get", "post", "put", "patch", "delete"):
                answer = getattr(client_for_admin, method)(path)
                assert answer.status_code in (401, 403, 405), (method, path)
                assert_clean(answer.content.decode())


class TestSupportSeesCountsOnly:
    def test_figures_are_statuses_and_numbers_only(self, stored):
        figures = support_figures.cv_counts_by_status(stored.company_id)
        assert set(figures) == {status for status, _ in CvFile.Status.choices}
        assert all(isinstance(count, int) for count in figures.values())
        assert figures["done"] == 1
        assert_clean(json.dumps(figures))

    def test_other_companies_are_not_counted(self, stored):
        assert support_figures.cv_counts_by_status(make_company().pk)["done"] == 0


class TestAdminScreensAndExportsHoldNoCandidateContent:
    def admin_get_routes(self):
        for route, view in all_routes():
            if any(issubclass(a, AdminAuthentication) for a in authenticators_of(view)):
                yield route

    def test_there_are_admin_routes_to_check(self):
        assert list(self.admin_get_routes())

    @pytest.mark.parametrize("role", ["super", "support"])
    def test_no_admin_route_returns_candidate_content(self, stored, role):
        admin = admin_client(role)
        for route in self.admin_get_routes():
            path = "/" + route.replace("<str:id>", str(stored.company_id)).replace(
                "<str:name>", "cvs_per_month"
            )
            for method in ("get", "options", "head"):
                answer = getattr(admin, method)(path)
                assert_clean(answer.content.decode())
                assert_clean(json.dumps(dict(answer.headers)))

    def test_the_audit_log_and_activity_list_hold_no_candidate_content(self, stored):
        admin = admin_client("super")
        admin.post(
            f"/api/admin/companies/{stored.company_id}/suspend/",
            {"reason": "A test of the audit log."},
            format="json",
        )
        from activity.models import ActivityEntry
        from audit.models import AuditEvent

        rows = list(AuditEvent.objects.all()) + list(ActivityEntry.objects.all())
        assert rows
        assert_clean(serializers.serialize("json", rows))

    def test_an_export_helper_can_reuse_the_check(self):
        with pytest.raises(AssertionError):
            assert_clean(f"report for {NAME}")


class TestLogsAndEmailsHoldNoCandidateContent:
    def test_the_pipeline_logs_nothing_from_the_cv_or_the_contact_details(
        self, stub_ai, real_pipeline, caplog
    ):
        caplog.set_level(logging.DEBUG)
        run_pipeline(make_cv())
        assert Candidate.objects.exists()
        assert_clean(caplog.text)

    def test_a_failing_step_logs_only_the_kind_of_error(self, stub_ai, real_pipeline, caplog):
        def broken(context):
            raise RuntimeError(CV_TEXT)

        processing.STEPS["scoring"] = broken
        caplog.set_level(logging.DEBUG)
        run_pipeline(make_cv())
        assert "RuntimeError" in caplog.text
        assert_clean(caplog.text)

    def test_an_answer_that_cannot_be_used_logs_nothing_from_it(
        self, real_pipeline, monkeypatch, caplog
    ):
        monkeypatch.setattr(client, "_send", lambda **call: AiAnswer(f"{NAME} {EMAIL}", 1, 1))
        caplog.set_level(logging.DEBUG)
        finished = run_pipeline(make_cv())
        assert finished.status == "failed"
        assert_clean(caplog.text)
        assert_clean(finished.failure_reason)

    def test_the_log_formatter_scrubs_contact_details_that_slip_through(self):
        record = logging.LogRecord(
            "x",
            logging.INFO,
            "f",
            1,
            f"saved phone={PHONE} {PHONE} {EMAIL} address=Home",
            None,
            None,
        )
        record.request_id = record.user_id = record.company_id = "-"
        line = logging_setup.RedactingFormatter().format(record)
        assert_clean(line)
        assert "7788" not in line and "REDACTED" in line

    def test_ordinary_log_lines_keep_dates_and_ids(self):
        text = "2026-11-14 job 12-34-56 version 3.12.1 finished"
        assert logging_setup.redact(text) == text

    def test_no_logger_call_in_the_cv_code_names_candidate_content(self):
        """The first rule is never to give a logger candidate data: look at what the logger
        calls of the CV code are given."""
        forbidden = {
            "contact",
            "profile",
            "text",
            "cv_text",
            "data",
            "answer",
            "raw_text",
            "summary",
            "name",
            "email",
            "phone",
            "address",
            "original_name",
            "content",
        }
        folder = pathlib.Path(importlib.import_module("cvs").__file__).parent
        offenders = []
        for source in folder.glob("*.py"):
            for node in ast.walk(ast.parse(source.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "logger"
                ):
                    for argument in [*node.args[1:], *[k.value for k in node.keywords]]:
                        for part in ast.walk(argument):
                            used = (
                                part.id
                                if isinstance(part, ast.Name)
                                else getattr(part, "attr", None)
                            )
                            if used in forbidden:
                                offenders.append(f"{source.name}:{node.lineno} {used}")
        assert not offenders, offenders

    def test_the_pipeline_sends_no_email(self, stored):
        assert mail.outbox == []
        from emailing.models import OutgoingEmail

        assert_clean(serializers.serialize("json", OutgoingEmail.objects.all()))

    def test_no_email_template_takes_candidate_values(self):
        from emailing.catalog import CATALOG

        banned = ("candidate", "cv", "contact", "profile", "resume", "phone", "address")
        for name, template in CATALOG.items():
            for variable in template.variables:
                assert not any(word in variable for word in banned), (name, variable)

    def test_email_code_never_imports_candidate_models(self):
        import emailing

        folder = pathlib.Path(emailing.__file__).parent
        for source in folder.glob("*.py"):
            text = source.read_text()
            assert "cvs.models" not in text and "from cvs" not in text, source.name


class TestAuditKindForAFutureException:
    def test_the_kind_exists_and_needs_a_written_reason(self):
        from audit.events import KINDS

        assert KINDS["admin.candidate_data_exception"].reason_required is True


class TestRemovedCandidateLeavesNoPersonalData:
    def test_nothing_of_the_candidate_is_left_in_the_database_after_removal(self, stored):
        candidates.remove_candidate(Candidate.objects.get(cv_file=stored))
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM cvs_cvcontact")
            assert cursor.fetchone()[0] == 0
        assert not CvProfile.objects.exists()
