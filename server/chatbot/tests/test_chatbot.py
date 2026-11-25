import io

import pytest
from docx import Document
from rest_framework.test import APIClient

from ai.models import AiModel, PromptVersion
from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from chatbot import documents
from chatbot.models import KnowledgeDocument
from cvs.tests.files import make_docx, make_encrypted_docx, make_pdf
from cvs.tests.test_ai_reading import set_setting
from platform_settings.service import get_setting

pytestmark = pytest.mark.django_db
URL = "/api/admin/chatbot/"
DOCS = f"{URL}documents/"
TEXT = b"The product ranks CVs against the requirements of a job.\nPricing starts with Starter."


@pytest.fixture
def boss():
    return admin_client("super")[0]


@pytest.fixture
def support():
    return admin_client("support")[0]


def real_docx(text="Plans are billed monthly in US dollars."):
    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def upload(client, name, data, url=DOCS, method="post"):
    sent = io.BytesIO(data)
    sent.name = name
    return getattr(client, method)(url, {"file": sent}, format="multipart")


def audited():
    return list(
        AuditEvent.objects.filter(kind__startswith="admin.chatbot").values_list("kind", flat=True)
    )


def code(response):
    return response.json()["error"]["code"]


def settings_body(**changes):
    body = {
        "enabled": False,
        "model": "",
        "prompt_version": 1,
        "visitor_questions_per_hour": 20,
        "max_question_length": 300,
        "max_answer_length": 1500,
        "daily_token_cap": 200000,
    }
    return {**body, **changes}


class TestWhoMayUseIt:
    def test_support_is_refused_everywhere(self, support):
        assert support.get(URL).status_code == 403
        assert support.put(URL, settings_body(), format="json").status_code == 403
        assert upload(support, "a.txt", TEXT).status_code == 403
        assert support.patch(f"{DOCS}1/", {"enabled": False}, format="json").status_code == 403
        assert upload(support, "a.txt", TEXT, f"{DOCS}1/", "put").status_code == 403
        assert support.delete(f"{DOCS}1/").status_code == 403
        assert not KnowledgeDocument.objects.exists()
        assert audited() == []

    def test_a_company_user_and_nobody_signed_in_are_refused(self):
        assert APIClient().get(URL).status_code == 401
        assert APIClient().post(DOCS, {}, format="multipart").status_code == 401

    def test_a_super_admin_reads_the_state(self, boss):
        body = boss.get(URL).json()
        assert body["settings"]["enabled"] is False
        assert body["settings"]["model"] == ""
        assert body["settings"]["prompt_version"] == 1
        assert body["settings"]["prompt_versions"] == [1]
        assert body["documents"] == []


class TestSettings:
    @pytest.fixture
    def model(self):
        return AiModel.objects.create(
            name="chat-model", input_price_per_million=1, output_price_per_million=2
        )

    def test_it_starts_off_with_the_platform_limits(self):
        assert get_setting("chatbot.enabled") is False
        assert get_setting("chatbot.model") == ""

    def test_changes_are_saved_and_audited_with_old_and_new_values(self, boss, model):
        body = settings_body(enabled=True, model="chat-model", max_question_length=200)
        response = boss.put(URL, body, format="json")
        assert response.status_code == 200, response.content
        assert get_setting("chatbot.enabled") is True
        assert get_setting("chatbot.model") == "chat-model"
        assert get_setting("chatbot.max_question_length") == 200
        event = AuditEvent.objects.get(kind="admin.chatbot_settings_changed")
        assert event.details["changes"]["max_question_length"] == {"old": 300, "new": 200}
        assert event.details["changes"]["enabled"] == {"old": False, "new": True}

    def test_saving_nothing_new_writes_no_audit_entry(self, boss):
        assert boss.put(URL, settings_body(), format="json").status_code == 200
        assert audited() == []

    def test_it_cannot_be_switched_on_without_a_model(self, boss):
        response = boss.put(URL, settings_body(enabled=True), format="json")
        assert response.status_code == 400
        assert "enabled" in response.json()["error"]["fields"]
        assert get_setting("chatbot.enabled") is False

    def test_the_model_must_be_in_the_list_and_switched_on(self, boss, model):
        assert boss.put(URL, settings_body(model="nope"), format="json").status_code == 400
        AiModel.objects.filter(pk=model.pk).update(enabled=False)
        assert boss.put(URL, settings_body(model="chat-model"), format="json").status_code == 400

    def test_the_prompt_version_must_exist_and_be_of_the_chatbot_kind(self, boss):
        assert boss.put(URL, settings_body(prompt_version=9), format="json").status_code == 400
        PromptVersion.objects.create(kind="chatbot", number=2, text="Second.")
        assert boss.put(URL, settings_body(prompt_version=2), format="json").status_code == 200
        assert get_setting("ai.chatbot_prompt_version") == 2

    @pytest.mark.parametrize(
        "change",
        [
            {"visitor_questions_per_hour": 0},
            {"max_question_length": 5},
            {"max_answer_length": 99999999},
            {"daily_token_cap": 10},
            {"enabled": "yes"},
            {"surprise": 1},
        ],
    )
    def test_bad_values_are_refused_and_nothing_changes(self, boss, change):
        assert boss.put(URL, settings_body(**change), format="json").status_code == 400
        assert audited() == []

    def test_a_model_in_use_by_the_chatbot_needs_a_replacement_to_be_switched_off(
        self, boss, model
    ):
        other = AiModel.objects.create(
            name="other-model", input_price_per_million=1, output_price_per_million=1
        )
        boss.put(URL, settings_body(enabled=True, model="chat-model"), format="json")
        response = boss.patch(
            f"/api/admin/ai/models/{model.pk}/",
            {"enabled": False, "reason": "Retired"},
            format="json",
        )
        assert response.status_code == 409
        moved = boss.patch(
            f"/api/admin/ai/models/{model.pk}/",
            {"enabled": False, "replacement": other.pk, "reason": "Retired"},
            format="json",
        )
        assert moved.status_code == 200, moved.content
        assert get_setting("chatbot.model") == "other-model"


class TestAddingDocuments:
    @pytest.mark.parametrize(
        ("name", "data"),
        [
            ("guide.txt", TEXT),
            ("guide.md", b"# Guide\n\nThe product ranks CVs against requirements."),
            ("guide.pdf", make_pdf(text="Pricing is billed monthly in US dollars")),
            ("guide.docx", real_docx()),
        ],
    )
    def test_each_kind_is_read_and_kept_as_text(self, boss, name, data):
        response = upload(boss, name, data)
        assert response.status_code == 201, response.content
        document = KnowledgeDocument.objects.get()
        assert document.name == name and document.enabled is True
        assert document.size_bytes == len(data) and len(document.text) > 20
        listed = response.json()["documents"][0]
        assert "text" not in listed and listed["characters"] == len(document.text)
        assert audited() == ["admin.chatbot_document_added"]

    def test_the_original_file_is_not_kept(self, boss):
        upload(boss, "guide.txt", TEXT)
        assert not hasattr(KnowledgeDocument, "file")
        assert {field.name for field in KnowledgeDocument._meta.get_fields()} == {
            "id", "name", "file_type", "size_bytes", "text", "enabled", "created_at", "updated_at",
        }  # fmt: skip

    @pytest.mark.parametrize(
        ("name", "data", "expected"),
        [
            ("guide.exe", TEXT, "document_wrong_type"),
            ("guide", TEXT, "document_wrong_type"),
            ("guide.txt", b"", "document_empty"),
            ("guide.txt", b"\xff\xfe\x00bad", "document_unreadable"),
            ("guide.txt", b"hi", "document_unreadable"),
            ("guide.pdf", TEXT, "type_mismatch"),
            ("guide.docx", make_pdf(), "type_mismatch"),
            ("guide.docx", make_encrypted_docx(), "password_protected"),
            ("guide.pdf", make_pdf(image_on_pages=(0,), text=""), "scanned_image"),
        ],
    )
    def test_bad_files_are_refused_in_plain_words(self, boss, name, data, expected):
        response = upload(boss, name, data)
        assert response.status_code == 400, response.content
        assert code(response) == expected
        assert not KnowledgeDocument.objects.exists()
        assert audited() == []

    def test_a_file_that_is_too_large_is_refused(self, boss):
        set_setting("chatbot.max_document_size_mb", 1)
        response = upload(boss, "big.txt", b"word " * 300_000)
        assert code(response) == "document_too_large"

    def test_a_document_with_too_many_characters_is_refused_not_cut(self, boss):
        set_setting("chatbot.max_document_characters", 1000)
        response = upload(boss, "long.txt", b"word " * 400)
        assert code(response) == "document_too_long"
        assert not KnowledgeDocument.objects.exists()

    def test_a_pdf_with_more_pages_than_are_read_is_refused(self, boss):
        response = upload(boss, "long.pdf", make_pdf(pages=16))
        assert code(response) == "document_too_long"

    def test_the_number_of_documents_is_limited(self, boss):
        set_setting("chatbot.max_documents", 2)
        assert upload(boss, "a.txt", TEXT).status_code == 201
        assert upload(boss, "b.txt", TEXT).status_code == 201
        assert code(upload(boss, "c.txt", TEXT)) == "document_limit"

    def test_the_total_size_is_limited(self, boss):
        set_setting("chatbot.max_total_size_mb", 1)
        set_setting("chatbot.max_document_characters", 1_000_000)
        one = b"word " * 120_000  # about 0.57 MB
        assert upload(boss, "a.txt", one).status_code == 201
        assert code(upload(boss, "b.txt", one)) == "document_total_limit"

    def test_the_allowed_types_are_a_platform_setting(self, boss):
        set_setting("chatbot.document_types", ["txt"])
        assert code(upload(boss, "a.md", TEXT)) == "document_wrong_type"
        assert upload(boss, "a.txt", TEXT).status_code == 201

    def test_unknown_fields_in_the_upload_are_refused(self, boss):
        sent = io.BytesIO(TEXT)
        sent.name = "a.txt"
        response = boss.post(DOCS, {"file": sent, "company": "1"}, format="multipart")
        assert response.status_code == 400


class TestChangingDocuments:
    @pytest.fixture
    def stored(self, boss):
        upload(boss, "guide.txt", TEXT)
        return KnowledgeDocument.objects.get()

    def test_switching_off_and_on_is_audited(self, boss, stored):
        url = f"{DOCS}{stored.pk}/"
        assert boss.patch(url, {"enabled": False}, format="json").status_code == 200
        stored.refresh_from_db()
        assert stored.enabled is False and documents.knowledge_texts() == []
        assert boss.patch(url, {"enabled": True}, format="json").status_code == 200
        assert [name for name, _ in documents.knowledge_texts()] == ["guide.txt"]
        assert audited().count("admin.chatbot_document_switched") == 2

    def test_switching_to_the_same_state_changes_nothing(self, boss, stored):
        response = boss.patch(f"{DOCS}{stored.pk}/", {"enabled": True}, format="json")
        assert response.status_code == 400 and code(response) == "nothing_changed"

    def test_replacing_keeps_the_place_and_the_state_and_is_audited(self, boss, stored):
        boss.patch(f"{DOCS}{stored.pk}/", {"enabled": False}, format="json")
        response = upload(
            boss,
            "guide2.md",
            b"# New\n\nNew text about the product and how it ranks every CV.",
            f"{DOCS}{stored.pk}/",
            "put",
        )
        assert response.status_code == 200, response.content
        stored.refresh_from_db()
        assert (stored.name, stored.enabled) == ("guide2.md", False)
        assert "New text about" in stored.text and KnowledgeDocument.objects.count() == 1
        assert "admin.chatbot_document_replaced" in audited()

    def test_a_bad_replacement_changes_nothing(self, boss, stored):
        before = stored.text
        response = upload(boss, "guide.exe", TEXT, f"{DOCS}{stored.pk}/", "put")
        assert response.status_code == 400
        stored.refresh_from_db()
        assert stored.text == before

    def test_replacing_does_not_count_the_old_file_twice(self, boss):
        set_setting("chatbot.max_documents", 1)
        set_setting("chatbot.max_total_size_mb", 1)
        set_setting("chatbot.max_document_characters", 1_000_000)
        upload(boss, "a.txt", b"word " * 120_000)
        stored = KnowledgeDocument.objects.get()
        response = upload(boss, "a.txt", b"word " * 120_000, f"{DOCS}{stored.pk}/", "put")
        assert response.status_code == 200

    def test_deleting_removes_the_document_and_is_audited(self, boss, stored):
        assert boss.delete(f"{DOCS}{stored.pk}/").status_code == 200
        assert not KnowledgeDocument.objects.exists()
        assert "admin.chatbot_document_deleted" in audited()

    def test_an_unknown_document_is_not_found(self, boss):
        assert boss.delete(f"{DOCS}999/").status_code == 404
        assert boss.patch(f"{DOCS}999/", {"enabled": True}, format="json").status_code == 404
        assert upload(boss, "a.txt", TEXT, f"{DOCS}999/", "put").status_code == 404


class TestPublicInformationOnly:
    def test_no_table_of_the_feature_points_at_company_or_candidate_data(self):
        from django.apps import apps

        from core.models import CompanyOwnedModel

        for model in apps.get_app_config("chatbot").get_models():
            assert not issubclass(model, CompanyOwnedModel)
            for field in model._meta.get_fields():
                assert not field.is_relation, f"{model.__name__}.{field.name} is a link"

    def test_no_audit_entry_holds_a_document_name_or_its_text(self, boss):
        upload(boss, "secret-looking-name.txt", TEXT)
        for event in AuditEvent.objects.filter(kind__startswith="admin.chatbot"):
            assert "secret-looking-name" not in str(event.details)
            assert "ranks CVs" not in str(event.details)

    def test_the_reading_of_files_is_the_shared_one(self):
        from cvs.file_checks import check_content, check_cv_file

        assert check_content("pdf", make_pdf()).problem is None
        assert check_cv_file("cv.pdf", make_pdf()).problem is None
        assert make_docx()  # the shared fixtures are what the checks are tested with
