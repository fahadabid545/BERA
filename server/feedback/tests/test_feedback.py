"""Feedback: sent by any signed-in person, read and moved along by both admin roles, counted in
the overview, and never copied into a log, an audit entry or an email."""

import logging
from datetime import timedelta

import pytest
from django.core import mail
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from companies.deletion import remove_company
from companies.tests.test_role_matrix import client_for as company_client
from core.tests.factories import make_company, make_company_user
from cvs.tests.test_ai_reading import set_setting
from feedback.models import Feedback
from signin.tests.models_for_tests import KINDS_OF_OBJECT

pytestmark = pytest.mark.django_db
SEND = "/api/company/feedback/"
LIST = "/api/admin/feedback/"
OVERVIEW = "/api/admin/dashboard/"
DETAIL = "/api/admin/dashboard/detail/"
SECRET_TEXT = "FAKE-SECRET-FEEDBACK-TEXT"
PAGE = "/company/projects"
DAY = timedelta(days=1)


def body(**over):
    return {"kind": "bug", "message": "Fake feedback text.", "page": PAGE, **over}


@pytest.fixture(params=["owner", "member"])
def person(request):
    return make_company_user(role=request.param)


@pytest.fixture(params=["super", "support"])
def admin(request):
    return admin_client(request.param)[0]


def send(person, **over):
    reply = company_client(person).post(SEND, body(**over), format="json")
    assert reply.status_code == 201, reply.json()


class TestSending:
    def test_every_signed_in_person_may_send_and_it_is_saved_as_new(self, person):
        send(person, kind="idea", message="Fake idea.")
        saved = Feedback.objects.get()
        assert (saved.kind, saved.message, saved.page, saved.status) == (
            "idea",
            "Fake idea.",
            PAGE,
            "new",
        )

    def test_the_company_and_person_come_from_the_sign_in(self, person):
        send(person)
        saved = Feedback.objects.get()
        assert (saved.company_id, saved.user_id) == (person.company_id, person.pk)

    def test_a_company_or_person_in_the_request_is_refused(self, person):
        other = make_company()
        reply = company_client(person).post(SEND, body(company=other.pk), format="json")
        assert reply.status_code == 400
        assert not Feedback.objects.exists()

    def test_the_message_is_stored_encrypted(self, person):
        send(person, message=SECRET_TEXT)
        with connection.cursor() as cursor:
            cursor.execute("select message from feedback_feedback")
            stored = cursor.fetchone()[0]
        assert SECRET_TEXT not in stored

    @pytest.mark.parametrize("kind", ["", "praise", None, 3])
    def test_an_unknown_kind_is_refused(self, person, kind):
        reply = company_client(person).post(SEND, body(kind=kind), format="json")
        assert reply.status_code == 400
        assert "kind" in reply.json()["error"]["fields"]

    @pytest.mark.parametrize("message", ["", "   ", None, 5, "bad\x00text"])
    def test_an_empty_or_unsupported_message_is_refused(self, person, message):
        reply = company_client(person).post(SEND, body(message=message), format="json")
        assert reply.status_code == 400
        assert "message" in reply.json()["error"]["fields"]

    def test_the_message_length_limit_is_a_platform_setting(self, person):
        set_setting("feedback.max_message_length", 10)
        assert (
            company_client(person).post(SEND, body(message="x" * 11), format="json").status_code
            == 400
        )
        assert (
            company_client(person).post(SEND, body(message="x" * 10), format="json").status_code
            == 201
        )

    @pytest.mark.parametrize(
        "page", ["", "/admin", "/companyx/../admin?a=1", "/company/projects?token=1", "/company/#x"]
    )
    def test_only_a_plain_company_page_is_accepted(self, person, page):
        reply = company_client(person).post(SEND, body(page=page), format="json")
        assert reply.status_code == 400
        assert "page" in reply.json()["error"]["fields"]

    def test_files_cannot_be_attached(self, person):
        reply = company_client(person).post(SEND, {**body(), "file": "x"}, format="json")
        assert reply.status_code == 400

    def test_nobody_signed_in_cannot_send(self):
        assert APIClient().post(SEND, body(), format="json").status_code == 401

    def test_feedback_is_not_readable_through_the_company_route(self, person):
        send(person)
        assert company_client(person).get(SEND).status_code == 405


class TestRateLimit:
    def test_ten_an_hour_per_person_by_default(self, person):
        client = company_client(person)
        answers = [client.post(SEND, body(), format="json").status_code for _ in range(11)]
        assert answers == [201] * 10 + [429]
        assert Feedback.objects.count() == 10

    def test_one_person_does_not_use_up_another_ones_allowance(self):
        first, second = make_company_user(), make_company_user()
        for _ in range(10):
            send(first)
        assert company_client(first).post(SEND, body(), format="json").status_code == 429
        send(second)

    def test_the_limit_is_a_platform_setting(self, person):
        set_setting("rate_limits.feedback_per_hour", 2)
        client = company_client(person)
        answers = [client.post(SEND, body(), format="json").status_code for _ in range(3)]
        assert answers == [201, 201, 429]


class TestAdminList:
    def test_both_roles_read_what_was_sent_with_company_and_person(self, admin, person):
        send(person, message="Fake message.")
        (item,) = admin.get(LIST).json()["items"]
        assert item["company"] == person.company.name
        assert item["user"] == person.name
        assert (item["kind"], item["message"], item["page"], item["status"]) == (
            "bug",
            "Fake message.",
            PAGE,
            "new",
        )
        assert "email" not in item

    def test_the_newest_comes_first(self, admin, person):
        send(person, message="first")
        send(person, message="second")
        assert [i["message"] for i in admin.get(LIST).json()["items"]] == ["second", "first"]

    def test_feedback_of_every_company_is_listed(self, admin):
        send(make_company_user())
        send(make_company_user())
        assert admin.get(LIST).json()["total"] == 2

    def test_filter_by_kind_and_status(self, admin, person):
        send(person, kind="bug")
        send(person, kind="idea")
        moved = admin.get(LIST, {"kind": "idea"}).json()["items"][0]
        admin.patch(f"{LIST}{moved['id']}/", {"status": "fixed"}, format="json")
        assert [i["kind"] for i in admin.get(LIST, {"kind": "idea"}).json()["items"]] == ["idea"]
        assert [i["kind"] for i in admin.get(LIST, {"status": "new"}).json()["items"]] == ["bug"]
        assert admin.get(LIST, {"status": "fixed", "kind": "bug"}).json()["total"] == 0

    def test_filter_by_date_includes_both_ends(self, admin, person):
        send(person, message="old")
        send(person, message="recent")
        old = Feedback.objects.order_by("created_at").first()
        Feedback.objects.filter(pk=old.pk).update(created_at=timezone.now() - 10 * DAY)
        today = timezone.localdate()
        recent = admin.get(LIST, {"since": (today - 2 * DAY).isoformat()}).json()["items"]
        assert [i["message"] for i in recent] == ["recent"]
        until = admin.get(LIST, {"until": (today - 5 * DAY).isoformat()}).json()["items"]
        assert [i["message"] for i in until] == ["old"]
        both = {"since": today.isoformat(), "until": today.isoformat()}
        assert admin.get(LIST, both).json()["total"] == 1

    @pytest.mark.parametrize(
        "query",
        [{"status": "open"}, {"kind": "praise"}, {"since": "soon"}, {"extra": "1"}],
    )
    def test_a_bad_filter_is_refused(self, admin, query):
        assert admin.get(LIST, query).status_code == 400

    def test_an_end_before_the_start_is_refused(self, admin):
        reply = admin.get(LIST, {"since": "2026-02-01", "until": "2026-01-01"})
        assert reply.status_code == 400

    def test_the_list_is_cut_at_the_platform_limit_with_the_real_total(self, admin, person):
        set_setting("feedback.list_limit", 2)
        for _ in range(3):
            send(person)
        reply = admin.get(LIST).json()
        assert (reply["total"], len(reply["items"])) == (3, 2)

    def test_a_company_person_cannot_use_the_admin_routes(self, person):
        client = company_client(person)
        send(person)
        assert client.get(LIST).status_code == 401
        item = Feedback.objects.get()
        assert (
            client.patch(f"{LIST}{item.pk}/", {"status": "fixed"}, format="json").status_code == 401
        )


class TestStatus:
    def make(self, person):
        send(person)
        return Feedback.objects.get()

    @pytest.mark.parametrize("status", ["reviewing", "fixed", "wont_fix", "new"])
    def test_both_roles_set_any_status(self, admin, person, status):
        item = self.make(person)
        reply = admin.patch(f"{LIST}{item.pk}/", {"status": status}, format="json")
        assert reply.status_code == 200
        item.refresh_from_db()
        assert item.status == status

    def test_a_note_can_be_written_with_or_without_a_status(self, admin, person):
        item = self.make(person)
        admin.patch(f"{LIST}{item.pk}/", {"note": "Fake internal note."}, format="json")
        item.refresh_from_db()
        assert (item.note, item.status) == ("Fake internal note.", "new")

    def test_the_note_length_is_a_platform_setting(self, admin, person):
        item = self.make(person)
        set_setting("feedback.max_note_length", 5)
        assert admin.patch(f"{LIST}{item.pk}/", {"note": "x" * 6}, format="json").status_code == 400

    def test_nothing_to_change_or_a_bad_status_is_refused(self, admin, person):
        item = self.make(person)
        assert admin.patch(f"{LIST}{item.pk}/", {}, format="json").status_code == 400
        reply = admin.patch(f"{LIST}{item.pk}/", {"status": "done"}, format="json")
        assert reply.status_code == 400

    def test_an_unknown_item_is_not_found(self, admin):
        reply = admin.patch(f"{LIST}00000000-0000-0000-0000-000000000000/", {"status": "fixed"})
        assert reply.status_code == 404

    def test_a_change_of_status_is_audited_without_the_message(self, admin, person):
        send(person, message=SECRET_TEXT)
        item = Feedback.objects.get()
        admin.patch(
            f"{LIST}{item.pk}/", {"status": "reviewing", "note": SECRET_TEXT}, format="json"
        )
        event = AuditEvent.objects.get(kind="admin.feedback_status_changed")
        assert event.company_id == person.company_id
        assert event.details == {
            "feedback_id": str(item.pk),
            "old_status": "new",
            "new_status": "reviewing",
        }
        assert SECRET_TEXT not in str(event.__dict__)

    def test_a_note_alone_or_the_same_status_is_not_a_status_change(self, admin, person):
        item = self.make(person)
        admin.patch(f"{LIST}{item.pk}/", {"note": "Fake note."}, format="json")
        admin.patch(f"{LIST}{item.pk}/", {"status": "new"}, format="json")
        assert not AuditEvent.objects.filter(kind="admin.feedback_status_changed").exists()


class TestAttention:
    def test_only_new_feedback_is_counted_for_both_roles(self, admin, person):
        send(person)
        send(person)
        assert admin.get(OVERVIEW).json()["pending"]["feedback"] == 2
        first = admin.get(LIST).json()["items"][0]
        admin.patch(f"{LIST}{first['id']}/", {"status": "reviewing"}, format="json")
        assert admin.get(OVERVIEW).json()["pending"]["feedback"] == 1

    def test_the_review_lists_new_feedback_without_its_text(self, admin, person):
        send(person, kind="idea", message=SECRET_TEXT)
        reply = admin.get(DETAIL, {"kind": "pending", "key": "feedback"}).json()
        assert reply["total"] == 1
        (item,) = reply["items"]
        assert (item["type"], item["company_id"], item["feedback_kind"]) == (
            "feedback",
            person.company_id,
            "idea",
        )
        assert SECRET_TEXT not in str(reply)


class TestPrivacy:
    def test_nothing_is_logged_or_emailed(self, admin, person, caplog):
        with caplog.at_level(logging.DEBUG):
            send(person, message=SECRET_TEXT)
            item = Feedback.objects.get()
            admin.get(LIST)
            admin.patch(
                f"{LIST}{item.pk}/", {"status": "fixed", "note": SECRET_TEXT}, format="json"
            )
            admin.get(OVERVIEW)
        assert SECRET_TEXT not in caplog.text
        assert mail.outbox == []

    def test_a_refused_message_is_not_logged_either(self, person, caplog):
        with caplog.at_level(logging.DEBUG):
            company_client(person).post(
                SEND, body(kind="praise", message=SECRET_TEXT), format="json"
            )
        assert SECRET_TEXT not in caplog.text


@pytest.mark.isolation
class TestCompanyData:
    @pytest.fixture(autouse=True)
    def stand_in_tables(self, db):
        """Deleting a company looks at every model that points at it, including the stand-ins the
        isolation tests register for the whole run, so their tables must exist here too."""
        with connection.schema_editor() as editor:
            for model in KINDS_OF_OBJECT.values():
                editor.create_model(model)

    def test_deleting_a_company_removes_its_feedback_and_only_its_feedback(self):
        gone, kept = make_company_user(), make_company_user()
        send(gone, message="gone")
        send(kept, message="kept")
        remove_company(gone.company_id)
        assert list(Feedback.objects.values_list("message", flat=True)) == ["kept"]
