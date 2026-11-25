"""The Terms and Privacy text, and the record that it was reviewed."""

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from platform_settings import legal_documents, legal_review

pytestmark = pytest.mark.django_db
URL = "/api/admin/settings/legal-review/"
TEXT = {"title": "Fake", "sections": [{"heading": "Fake heading", "paragraphs": ["Fake text."]}]}


@pytest.fixture
def written(monkeypatch):
    """Both documents hold (fake) text, so there is something to review."""
    monkeypatch.setattr(legal_documents, "TERMS", dict(TEXT))
    monkeypatch.setattr(legal_documents, "PRIVACY", dict(TEXT))


@pytest.fixture
def boss():
    return admin_client("super")[0]


def mark(client, name="Fake Reviewer", **extra):
    return client.put(URL, {"reviewed": True, "reviewer_name": name, **extra}, format="json")


def events(kind):
    return AuditEvent.objects.filter(kind=kind)


class TestThePublicText:
    def test_is_empty_until_the_owner_supplies_it(self):
        reply = APIClient().get("/api/legal/")
        assert reply.status_code == 200
        assert reply.json() == {
            "terms": {"title": "Terms", "sections": []},
            "privacy": {"title": "Privacy", "sections": []},
        }

    def test_says_nothing_about_a_review(self, written, boss):
        mark(boss)
        assert set(APIClient().get("/api/legal/").json()) == {"terms", "privacy"}
        assert "review" not in APIClient().get("/api/legal/").content.decode().lower()

    def test_no_legal_wording_is_written_in_the_code(self):
        assert legal_documents.TERMS["sections"] == []
        assert legal_documents.PRIVACY["sections"] == []

    def test_a_change_to_either_text_changes_the_version(self, monkeypatch):
        before = legal_documents.current_version()
        monkeypatch.setattr(legal_documents, "TERMS", dict(TEXT))
        assert legal_documents.current_version() != before


class TestMarkingItReviewed:
    def test_starts_as_not_reviewed(self, boss):
        reply = boss.get(URL)
        assert reply.status_code == 200
        assert reply.json()["reviewed"] is False
        assert legal_review.is_reviewed() is False

    def test_stores_who_when_and_which_text(self, boss, written):
        reply = mark(boss, reviewed_on="2026-01-15")
        body = reply.json()
        assert (body["reviewed"], body["reviewer_name"], body["reviewed_on"]) == (
            True,
            "Fake Reviewer",
            "2026-01-15",
        )
        assert body["reviewed_version"] == legal_documents.current_version()
        assert legal_review.is_reviewed() is True

    def test_the_date_defaults_to_today(self, boss, written):
        assert mark(boss).json()["reviewed_on"] == date.today().isoformat()

    def test_a_future_date_is_refused(self, boss, written):
        future = (date.today() + timedelta(days=2)).isoformat()
        assert mark(boss, reviewed_on=future).status_code == 400
        assert legal_review.is_reviewed() is False

    def test_needs_the_reviewers_name(self, boss, written):
        reply = boss.put(URL, {"reviewed": True}, format="json")
        assert reply.status_code == 400
        assert "reviewer_name" in reply.json()["error"]["fields"]
        assert mark(boss, name="  ").status_code == 400

    def test_cannot_review_text_that_is_not_there(self, boss):
        reply = mark(boss)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "nothing_to_review")
        assert legal_review.is_reviewed() is False

    def test_only_a_real_yes_or_no_counts(self, boss, written):
        assert (
            boss.put(URL, {"reviewed": "yes", "reviewer_name": "x"}, format="json").status_code
            == 400
        )


class TestTakingItBack:
    def test_clears_the_status(self, boss, written):
        mark(boss)
        reply = boss.put(URL, {"reviewed": False}, format="json")
        assert reply.json()["reviewed"] is False
        assert legal_review.is_reviewed() is False

    def test_clearing_when_not_reviewed_changes_nothing(self, boss):
        boss.put(URL, {"reviewed": False}, format="json")
        assert not events("admin.legal_review_cleared").exists()


class TestWhenTheTextChanges:
    def test_the_review_goes_back_to_not_reviewed_by_itself(self, boss, written, monkeypatch):
        mark(boss)
        assert legal_review.is_reviewed() is True
        monkeypatch.setattr(
            legal_documents,
            "PRIVACY",
            {**TEXT, "sections": [{"heading": "New", "paragraphs": ["x"]}]},
        )
        assert legal_review.is_reviewed() is False
        assert boss.get(URL).json()["reviewed"] is False
        assert events("admin.legal_review_reset").count() == 1

    def test_the_reset_is_recorded_once(self, boss, written, monkeypatch):
        mark(boss)
        monkeypatch.setattr(legal_documents, "TERMS", {**TEXT, "title": "Changed"})
        legal_review.status()
        legal_review.status()
        assert events("admin.legal_review_reset").count() == 1

    def test_the_new_text_can_be_reviewed_again(self, boss, written, monkeypatch):
        mark(boss)
        monkeypatch.setattr(legal_documents, "TERMS", {**TEXT, "title": "Changed"})
        assert legal_review.is_reviewed() is False
        mark(boss, name="Other Reviewer")
        assert legal_review.is_reviewed() is True


class TestSuperAdminOnly:
    def test_support_cannot_read_or_change_it(self, written):
        support = admin_client("support")[0]
        assert support.get(URL).status_code == 403
        assert mark(support).status_code == 403
        assert legal_review.is_reviewed() is False

    def test_nobody_signed_out_can(self):
        assert APIClient().get(URL).status_code in (401, 403)
        assert APIClient().put(URL, {"reviewed": False}, format="json").status_code in (401, 403)


class TestTheAuditLog:
    def test_turning_it_on_and_off_is_recorded_without_the_reviewers_name(self, boss, written):
        mark(boss)
        boss.put(URL, {"reviewed": False}, format="json")
        marked = events("admin.legal_review_marked").get()
        cleared = events("admin.legal_review_cleared").get()
        assert marked.actor_kind == "admin"
        assert marked.details == {"version": legal_documents.current_version()}
        assert cleared.actor_kind == "admin"
        assert "Fake Reviewer" not in str(
            list(AuditEvent.objects.values_list("details", flat=True))
        )
