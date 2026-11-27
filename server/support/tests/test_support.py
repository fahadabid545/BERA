"""Support: the agent talks with a person and hands a problem to the team as a ticket; the team
reads it, asks, works on it and closes it; the person sees the status."""

import json

import pytest
from django.db import connection
from rest_framework.test import APIClient

from ai import client
from ai.client import AiAnswer, AiUnavailable
from ai.default_prompts import SUPPORT_PROMPT
from ai.models import AiCall
from ai.prompt_versions import SUPPORT, prompt_text
from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from companies.deletion import remove_company
from companies.tests.test_role_matrix import client_for as company_client
from core.tests.factories import make_company, make_company_user
from cvs.tests.test_ai_reading import set_setting
from signin.tests.models_for_tests import KINDS_OF_OBJECT
from support.models import SupportChat, SupportChatMessage, SupportTicket, TicketMessage

pytestmark = pytest.mark.django_db
CHAT = "/api/company/support/chat/"
TICKETS = "/api/company/support/tickets/"
ADMIN = "/api/admin/support/tickets/"
SECRET = "FAKE-SECRET-SUPPORT-TEXT"
HANDOVER = {
    "escalate": {
        "title": "Cannot upload a CV",
        "category": "bug",
        "summary": "The person cannot upload a CV.",
        "what_happened": "The upload button does nothing.",
        "expected": "The CV is added to the project.",
        "steps": "Open a project and press Upload.",
        "reply": "I have told the support team.",
    }
}


@pytest.fixture
def provider(monkeypatch):
    class Provider:
        sent = []
        replies = [{"reply": "Try refreshing the page."}]
        failure = None

    def fake_send(**kwargs):
        Provider.sent.append(kwargs)
        if Provider.failure:
            raise Provider.failure
        reply = Provider.replies.pop(0) if len(Provider.replies) > 1 else Provider.replies[0]
        return AiAnswer(
            text=reply if isinstance(reply, str) else json.dumps(reply), tokens_in=10, tokens_out=5
        )

    Provider.sent = []
    Provider.replies = [{"reply": "Try refreshing the page."}]
    Provider.failure = None
    monkeypatch.setattr(client, "_send", fake_send)
    return Provider


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner(company):
    return make_company_user(company, role="owner")


@pytest.fixture
def member(company):
    return make_company_user(company, role="member")


def say(account, text, chat_id=None):
    body = {"text": text, **({"chat_id": chat_id} if chat_id else {})}
    return company_client(account).post(CHAT, body, format="json")


def ticket_from(owner, provider):
    provider.replies = [HANDOVER]
    response = say(owner, "I cannot upload a CV")
    assert response.status_code == 200, response.content
    return SupportTicket.objects.get(pk=response.json()["ticket"]["id"])


class TestTheAgent:
    def test_the_first_support_prompt_is_ready(self):
        assert prompt_text(SUPPORT, 1) == SUPPORT_PROMPT

    def test_a_plain_answer_is_shown_and_no_ticket_is_made(self, owner, provider):
        body = say(owner, "How do I add a project?").json()
        assert body["reply"] == "Try refreshing the page." and body["ticket"] is None
        assert SupportTicket.objects.count() == 0
        chat = SupportChat.objects.get(pk=body["chat_id"])
        assert [item.role for item in chat.messages.all()] == ["user", "assistant"]

    def test_the_agent_asks_a_question_and_the_chat_goes_on(self, owner, provider):
        provider.replies = [{"reply": "Which page are you on?"}, {"reply": "Thanks."}]
        first = say(owner, "It does not work").json()
        second = say(owner, "The projects page", first["chat_id"]).json()
        assert second["chat_id"] == first["chat_id"]
        earlier = json.loads(provider.sent[-1]["text"])["earlier_messages"]
        assert [item["text"] for item in earlier] == ["It does not work", "Which page are you on?"]

    def test_a_handover_makes_a_formatted_ticket(self, owner, provider):
        ticket = ticket_from(owner, provider)
        assert (ticket.title, ticket.category, ticket.status) == (
            "Cannot upload a CV",
            "bug",
            "open",
        )
        assert ticket.summary and ticket.what_happened and ticket.expected and ticket.steps
        assert (
            ticket.number == 1
            and ticket.user_id == owner.pk
            and ticket.company_id == owner.company_id
        )
        chat = SupportChat.objects.get()
        assert chat.ticket_id == ticket.pk

    def test_the_reply_after_a_handover_is_the_agents_own_sentence(self, owner, provider):
        provider.replies = [HANDOVER]
        assert say(owner, "x problem").json()["reply"] == "I have told the support team."

    def test_a_chat_that_reached_the_team_is_closed(self, owner, provider):
        provider.replies = [HANDOVER]
        chat_id = say(owner, "x problem").json()["chat_id"]
        response = say(owner, "another thing", chat_id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "support_chat_closed"

    def test_ticket_numbers_count_up(self, owner, provider):
        first = ticket_from(owner, provider)
        second = ticket_from(owner, provider)
        assert (first.number, second.number) == (1, 2)

    def test_an_unknown_category_becomes_other(self, owner, provider):
        provider.replies = [{"escalate": {**HANDOVER["escalate"], "category": "weird"}}]
        say(owner, "problem")
        assert SupportTicket.objects.get().category == "other"

    def test_long_parts_are_cut_to_the_limit(self, owner, provider):
        set_setting("support.max_field_length", 50)
        provider.replies = [{"escalate": {**HANDOVER["escalate"], "summary": "S" * 500}}]
        say(owner, "problem")
        assert len(SupportTicket.objects.get().summary) == 50

    @pytest.mark.parametrize("failure", [AiUnavailable("down")])
    def test_when_the_agent_cannot_answer_the_team_gets_the_message(self, owner, provider, failure):
        provider.failure = failure
        body = say(owner, f"Please help {SECRET}").json()
        assert body["ticket"] is not None
        ticket = SupportTicket.objects.get()
        assert SECRET in ticket.what_happened and ticket.category == "other"

    @pytest.mark.parametrize(
        "reply", ["not json", {"unrelated": 1}, {"reply": ""}, {"escalate": {"title": ""}}]
    )
    def test_an_unusable_answer_also_goes_to_the_team(self, owner, provider, reply):
        provider.replies = [reply]
        assert say(owner, "help me please").json()["ticket"] is not None

    def test_a_long_chat_is_handed_over_without_asking_the_ai_again(self, owner, provider):
        set_setting("support.max_user_messages_per_chat", 2)
        chat_id = say(owner, "one").json()["chat_id"]
        say(owner, "two", chat_id)
        calls = len(provider.sent)
        body = say(owner, "three", chat_id).json()
        assert body["ticket"] is not None and len(provider.sent) == calls

    def test_the_ai_is_sent_only_the_message_the_history_and_public_documents(
        self, owner, provider
    ):
        say(owner, "How do I upload?")
        data = json.loads(provider.sent[-1]["text"])
        assert set(data) == {"documents", "earlier_messages", "message"}
        assert provider.sent[-1]["instructions"] == SUPPORT_PROMPT
        assert AiCall.objects.get().purpose == "support"

    def test_a_message_is_checked(self, owner, provider):
        for body in ({"text": ""}, {"text": "x" * 5000}, {}, {"text": "hi", "extra": 1}):
            assert company_client(owner).post(CHAT, body, format="json").status_code == 400

    def test_nobody_but_a_company_person_may_talk_to_it(self, provider):
        assert APIClient().post(CHAT, {"text": "hi"}, format="json").status_code == 401
        assert (
            admin_client("support")[0].post(CHAT, {"text": "hi"}, format="json").status_code == 401
        )

    def test_another_persons_chat_is_not_found_even_in_the_same_company(
        self, owner, member, provider
    ):
        chat_id = say(member, "hello there").json()["chat_id"]
        assert say(owner, "mine now", chat_id).status_code == 404
        assert company_client(owner).get(f"{CHAT}{chat_id}/").status_code == 404
        assert company_client(member).get(f"{CHAT}{chat_id}/").status_code == 200

    def test_what_was_written_is_stored_encrypted(self, owner, provider):
        provider.replies = [{"escalate": {**HANDOVER["escalate"], "summary": SECRET}}]
        say(owner, f"say {SECRET}")
        with connection.cursor() as cursor:
            for table, column in (
                ("support_supportticket", "summary"),
                ("support_supportchatmessage", "text"),
            ):
                cursor.execute(f"select {column} from {table}")
                assert all(SECRET not in str(row[0]) for row in cursor.fetchall())

    def test_the_agent_is_not_logged(self, owner, provider, caplog):
        with caplog.at_level("DEBUG"):
            say(owner, f"private {SECRET}")
        assert SECRET not in caplog.text


class TestTheTicketsOfAPerson:
    def test_a_person_sees_their_own_tickets_with_the_status(self, owner, provider):
        ticket_from(owner, provider)
        rows = company_client(owner).get(TICKETS).json()["tickets"]
        assert [(row["number"], row["status"], row["title"]) for row in rows] == [
            (1, "open", "Cannot upload a CV")
        ]

    def test_a_member_does_not_see_anothers_ticket_but_the_owner_sees_all(
        self, owner, member, provider
    ):
        ticket = ticket_from(member, provider)
        assert company_client(owner).get(TICKETS).json()["tickets"][0]["id"] == str(ticket.pk)
        other_member = make_company_user(owner.company, role="member")
        assert company_client(other_member).get(TICKETS).json()["tickets"] == []
        assert company_client(other_member).get(f"{TICKETS}{ticket.pk}/").status_code == 404

    def test_another_companys_ticket_is_not_found(self, owner, provider):
        ticket = ticket_from(owner, provider)
        stranger = make_company_user(make_company(), role="owner")
        assert company_client(stranger).get(f"{TICKETS}{ticket.pk}/").status_code == 404
        assert company_client(stranger).get(TICKETS).json()["tickets"] == []

    def test_the_ticket_shows_every_part_and_the_conversation(self, owner, provider):
        ticket = ticket_from(owner, provider)
        body = company_client(owner).get(f"{TICKETS}{ticket.pk}/").json()
        assert body["what_happened"] and body["steps"] and body["messages"] == []
        assert "company" not in body and "handled_by" not in body  # admin-side facts

    def test_a_reply_to_the_teams_question_returns_it_to_the_team(self, owner, provider):
        ticket = ticket_from(owner, provider)
        admin_client("support")[0].patch(
            f"{ADMIN}{ticket.pk}/", {"message": "Which browser?"}, format="json"
        )
        assert SupportTicket.objects.get().status == "needs_reply"
        response = company_client(owner).post(
            f"{TICKETS}{ticket.pk}/", {"text": "Firefox"}, format="json"
        )
        assert response.status_code == 200
        assert SupportTicket.objects.get().status == "working"
        assert [m["author"] for m in response.json()["messages"]] == ["admin", "system", "user"]

    def test_a_reply_to_a_completed_ticket_reopens_it(self, owner, provider):
        ticket = ticket_from(owner, provider)
        SupportTicket.objects.filter(pk=ticket.pk).update(status="completed")
        company_client(owner).post(
            f"{TICKETS}{ticket.pk}/", {"text": "Still broken"}, format="json"
        )
        assert SupportTicket.objects.get().status == "open"

    def test_a_closed_ticket_takes_no_reply(self, owner, provider):
        ticket = ticket_from(owner, provider)
        SupportTicket.objects.filter(pk=ticket.pk).update(status="closed")
        response = company_client(owner).post(
            f"{TICKETS}{ticket.pk}/", {"text": "hello?"}, format="json"
        )
        assert response.status_code == 409 and response.json()["error"]["code"] == "ticket_closed"

    def test_a_visitor_is_refused(self, provider):
        assert APIClient().get(TICKETS).status_code == 401


class TestTheTeam:
    def test_open_tickets_are_listed_with_who_and_which_company(self, owner, provider):
        ticket_from(owner, provider)
        body = admin_client("support")[0].get(ADMIN).json()
        row = body["items"][0]
        assert (body["total"], body["open_count"]) == (1, 1)
        assert row["company"] == owner.company.name and row["user"] == owner.name
        assert row["number"] == 1 and row["status"] == "open"

    def test_finished_tickets_are_hidden_unless_asked_for(self, owner, provider):
        ticket = ticket_from(owner, provider)
        SupportTicket.objects.filter(pk=ticket.pk).update(status="completed")
        admin = admin_client("support")[0]
        assert admin.get(ADMIN).json()["items"] == []
        assert len(admin.get(f"{ADMIN}?status=completed").json()["items"]) == 1

    def test_the_list_can_be_filtered_by_category(self, owner, provider):
        ticket_from(owner, provider)
        admin = admin_client("support")[0]
        assert len(admin.get(f"{ADMIN}?category=bug").json()["items"]) == 1
        assert admin.get(f"{ADMIN}?category=billing").json()["items"] == []
        assert admin.get(f"{ADMIN}?status=nope").status_code == 400

    def test_a_ticket_is_read_in_full_with_the_company_and_person(self, owner, provider):
        ticket = ticket_from(owner, provider)
        body = admin_client("super")[0].get(f"{ADMIN}{ticket.pk}/").json()
        assert body["summary"] and body["user"] == owner.name and body["handled_by"] is None

    def test_asking_the_person_a_question_waits_for_their_reply(self, owner, provider):
        ticket = ticket_from(owner, provider)
        admin, who = admin_client("support")
        body = admin.patch(
            f"{ADMIN}{ticket.pk}/", {"message": "Which browser?"}, format="json"
        ).json()
        assert body["status"] == "needs_reply" and body["handled_by"] == who.name
        assert [(m["author"], m["text"]) for m in body["messages"]] == [
            ("admin", "Which browser?"),
            ("system", "Waiting for your reply"),
        ]

    def test_the_status_goes_through_working_completed_and_closed(self, owner, provider):
        ticket = ticket_from(owner, provider)
        admin = admin_client("support")[0]
        for status, word in (
            ("working", "Working on it"),
            ("completed", "Completed"),
            ("closed", "Closed"),
        ):
            body = admin.patch(f"{ADMIN}{ticket.pk}/", {"status": status}, format="json").json()
            assert body["status"] == status and body["messages"][-1]["text"] == word
        assert SupportTicket.objects.get().closed_at is not None
        company_status = company_client(owner).get(TICKETS).json()["tickets"][0]["status"]
        assert company_status == "closed"

    def test_reopening_clears_the_closing_time(self, owner, provider):
        ticket = ticket_from(owner, provider)
        admin = admin_client("support")[0]
        admin.patch(f"{ADMIN}{ticket.pk}/", {"status": "closed"}, format="json")
        admin.patch(f"{ADMIN}{ticket.pk}/", {"status": "open"}, format="json")
        assert SupportTicket.objects.get().closed_at is None

    def test_a_change_of_status_is_audited_without_any_text(self, owner, provider):
        ticket = ticket_from(owner, provider)
        admin_client("support")[0].patch(
            f"{ADMIN}{ticket.pk}/", {"status": "working", "message": SECRET}, format="json"
        )
        event = AuditEvent.objects.get(kind="admin.support_ticket_status_changed")
        assert event.company_id == owner.company_id
        assert event.details == {"ticket_number": 1, "old_status": "open", "new_status": "working"}
        assert SECRET not in json.dumps(event.details)

    def test_a_message_with_no_change_of_status_is_not_audited(self, owner, provider):
        ticket = ticket_from(owner, provider)
        SupportTicket.objects.filter(pk=ticket.pk).update(status="needs_reply")
        admin_client("support")[0].patch(
            f"{ADMIN}{ticket.pk}/", {"message": "Any news?"}, format="json"
        )
        assert not AuditEvent.objects.filter(kind="admin.support_ticket_status_changed").exists()

    def test_an_empty_change_or_a_bad_status_is_refused(self, owner, provider):
        ticket = ticket_from(owner, provider)
        admin = admin_client("support")[0]
        for body in ({}, {"status": "nope"}, {"message": ""}, {"message": "x" * 5000}):
            assert admin.patch(f"{ADMIN}{ticket.pk}/", body, format="json").status_code == 400

    def test_an_unknown_ticket_is_not_found(self, owner):
        admin = admin_client("support")[0]
        assert admin.get(f"{ADMIN}2b9d9a8e-5d58-4d58-9d58-5d589d589d58/").status_code == 404

    def test_a_company_person_and_a_visitor_are_refused(self, owner, provider):
        ticket = ticket_from(owner, provider)
        assert company_client(owner).get(ADMIN).status_code == 401
        assert APIClient().get(f"{ADMIN}{ticket.pk}/").status_code == 401


@pytest.mark.isolation
class TestCompanyData:
    @pytest.fixture(autouse=True)
    def stand_in_tables(self, db):
        """Deleting a company looks at every model that points at it, including the stand-ins the
        isolation tests register for the whole run, so their tables must exist here too."""
        with connection.schema_editor() as editor:
            for model in KINDS_OF_OBJECT.values():
                editor.create_model(model)

    def test_deleting_a_company_removes_its_support_data_and_only_its_data(self, provider):
        gone, kept = make_company_user(role="owner"), make_company_user(role="owner")
        for person in (gone, kept):
            ticket = ticket_from(person, provider)
            TicketMessage.objects.create(
                company_id=ticket.company_id, ticket=ticket, author="admin", text="hello"
            )
        remove_company(gone.company_id)
        assert list(SupportTicket.objects.values_list("company_id", flat=True)) == [kept.company_id]
        assert TicketMessage.objects.count() == 1
        assert SupportChat.objects.count() == 1 and SupportChatMessage.objects.count() == 2
