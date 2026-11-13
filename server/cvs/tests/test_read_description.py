import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document
from rest_framework.test import APIClient

from core import middleware
from core.tests.factories import make_company, make_company_user, start_session_for
from cvs.models import CvFile
from cvs.tests.files import make_docx, make_pdf
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache

pytestmark = pytest.mark.django_db
URL = "/api/company/projects/read-description/"
DESCRIPTION = "We are hiring a senior backend engineer with strong Python and SQL skills. " * 3


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def word(text):
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def send(client, name, data):
    return client.post(URL, {"files": SimpleUploadedFile(name, data)}, format="multipart")


@pytest.fixture
def client():
    return sign_in(make_company())


class TestReadingTheFile:
    def test_a_word_file_gives_its_text(self, client):
        body = send(client, "job.docx", word(DESCRIPTION)).json()
        assert body["text"] == DESCRIPTION.strip()
        assert body["trimmed"] is False

    def test_a_pdf_gives_its_text(self, client):
        body = send(
            client, "job.pdf", make_pdf(text="Senior backend engineer needed for payments team")
        ).json()
        assert body["text"] == "Senior backend engineer needed for payments team"

    def test_a_member_may_use_it(self):
        company = make_company()
        sign_in(company)  # the owner
        member = sign_in(company, role="member")
        assert send(member, "job.docx", word(DESCRIPTION)).status_code == 200

    def test_text_longer_than_a_description_is_cut_to_fit_and_flagged(self, client):
        set_setting("projects.description_max_length", 500)
        body = send(client, "job.docx", word("Backend engineer with Python. " * 100)).json()
        assert body["trimmed"] is True
        assert len(body["text"]) <= 500


class TestTheFileIsNotKept:
    def test_nothing_is_stored_and_nothing_is_counted(self, client, settings):
        from usage.models import UsageCounter

        send(client, "job.docx", word(DESCRIPTION))
        assert not CvFile.objects.exists()
        root = settings.PRIVATE_FILES_ROOT
        assert not root.exists() or [p for p in root.rglob("*") if p.is_file()] == []
        assert UsageCounter.objects.count() == 0


class TestFileProblems:
    @pytest.mark.parametrize(
        "name,data,message",
        [
            ("job.txt", b"hello", "Only PDF or DOCX files can be uploaded."),
            ("job.pdf", b"", "This file is empty."),
            ("job.pdf", make_docx(), None),
            ("job.docx", make_docx(extra_parts={"word/vbaProject.bin": b"x"}), None),
            (
                "job.pdf",
                b"%PDF-1.7\n" + b"\xff junk" * 50,
                "This file looks damaged and could not be read.",
            ),
        ],
    )
    def test_a_bad_file_gets_a_message_next_to_the_file_field(self, client, name, data, message):
        response = send(client, name, data)
        assert response.status_code == 400
        fields = response.json()["error"]["fields"]
        assert "file" in fields
        if message:
            assert fields["file"] == message

    def test_a_scanned_pdf_gets_the_scanned_message(self, client):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(612, 792)
        buffer = io.BytesIO()
        writer.write(buffer)
        response = send(client, "scan.pdf", buffer.getvalue())
        assert response.json()["error"]["fields"]["file"] == (
            "This looks like a scanned image. Please upload a text-based PDF or a Word file."
        )

    def test_a_file_with_no_readable_text_says_we_could_not_read_it(self, client):
        response = send(client, "empty.docx", word("   "))
        assert response.status_code == 400
        assert response.json()["error"]["fields"]["file"] == "We could not read this file."

    def test_no_file_is_a_form_mistake(self, client):
        response = client.post(URL, {}, format="multipart")
        assert response.status_code == 400
        assert "file" in response.json()["error"]["fields"]

    def test_two_files_are_refused(self, client):
        sent = [
            SimpleUploadedFile("a.docx", word(DESCRIPTION)),
            SimpleUploadedFile("b.docx", word(DESCRIPTION)),
        ]
        response = client.post(URL, {"files": sent}, format="multipart")
        assert response.status_code == 400
        assert response.json()["error"]["fields"]["file"] == "Choose one file."

    def test_too_large_a_file_is_refused(self, client):
        set_setting("uploads.max_file_size_mb", 1)
        response = send(client, "big.docx", make_docx() + b"0" * (1024 * 1024))
        assert response.json()["error"]["fields"]["file"] == "This file is larger than 1 MB."


class TestAccess:
    def test_nobody_signed_in_is_refused(self):
        assert APIClient().post(URL, {}, format="multipart").status_code == 401

    def test_only_post_is_allowed(self, client):
        assert client.get(URL).status_code == 405

    def test_it_counts_against_the_upload_allowance(self, client):
        set_setting("rate_limits.upload_files_per_10_minutes", 2)
        assert send(client, "job.docx", word(DESCRIPTION)).status_code == 200
        assert send(client, "job.docx", word(DESCRIPTION)).status_code == 200
        assert send(client, "job.docx", word(DESCRIPTION)).status_code == 429

    def test_the_route_may_take_a_file_sized_request_and_does_not_clash_with_a_project(self):
        assert middleware.is_upload_route("/api/company/projects/read-description/")
        assert not middleware.is_upload_route("/api/company/projects/read-description/x/")
