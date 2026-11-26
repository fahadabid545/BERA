import json

import pytest
from django.db import connection
from rest_framework.test import APIClient

from ai import client
from ai.client import AiAnswer, AiBusy, AiUnavailable
from ai.default_prompts import AGENT_PROMPT
from ai.models import AiCall
from ai.prompt_versions import ASK, prompt_text
from assistant import tools
from assistant.models import AgentChat, AgentMessage
from core.tests.factories import make_company, make_company_user, start_session_for
from cvs.models import AtsScore, Candidate
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add
from plans.limits import MONTHLY_AI_TOKEN_CAP
from plans.models import LimitOverride, Subscription
from usage import service as usage

pytestmark = pytest.mark.django_db
ASK_URL = "/api/company/assistant/ask/"
CHATS = "/api/company/assistant/chats/"
# Obviously fake private details that must never reach the AI.
FAKE_NAME = "Zed Quokka"
FAKE_FILE = "quokka-secret-cv.pdf"
FAKE_EMAIL = "quokka@example.com"
FAKE_PHONE = "+1 555 010 4242"
PRIVATE = (FAKE_NAME, FAKE_FILE, FAKE_EMAIL, FAKE_PHONE, "Quokka")


@pytest.fixture
def tenant():
    return Tenant(make_plan())


@pytest.fixture
def provider(monkeypatch):
    """What the AI is sent, and what it answers: `provider.replies` are used one after another
    (the last one repeats), or set `provider.failure`."""

    class Provider:
        sent = []
        replies = [{"answer": "Nothing to say.", "suggestions": []}]
        failure = None

    def fake_send(**kwargs):
        Provider.sent.append(kwargs)
        if Provider.failure:
            raise Provider.failure
        reply = Provider.replies.pop(0) if len(Provider.replies) > 1 else Provider.replies[0]
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return AiAnswer(text=text, tokens_in=100, tokens_out=20)

    Provider.sent = []
    Provider.replies = [{"answer": "Nothing to say.", "suggestions": []}]
    Provider.failure = None
    monkeypatch.setattr(client, "_send", fake_send)
    return Provider


def sent_data(provider, index=-1):
    return json.loads(provider.sent[index]["text"])


def with_results(tenant):
    """Two scored candidates: the first has every detail; the second is weaker."""
    best = add(tenant, FAKE_FILE, 90, ats=70, who=FAKE_NAME)
    best.contact.phone = FAKE_PHONE
    best.contact.email = FAKE_EMAIL
    best.contact.save()
    best.profile.content = {"years_of_experience": 6, "jobs": [{"title": "x"}, {"title": "y"}]}
    best.profile.save()
    other = add(tenant, "other.pdf", 40, ats=95)
    other.profile.content = {"years_of_experience": 12, "jobs": []}
    other.profile.save()
    return Candidate.objects.get(cv_file=best), Candidate.objects.get(cv_file=other)


def reference(candidate):
    return tools.candidate_reference(candidate.pk)


def project_ref(tenant):
    return tools.project_reference(tenant.project.pk)


def ask(who, question="Who is best?", **extra):
    return who.post(ASK_URL, {"question": question, **extra}, format="json")


def call(name, **arguments):
    return {"call": {"name": name, "arguments": arguments}}


def member_client(tenant, role="member"):
    person = make_company_user(tenant.company, role=role)
    issued = start_session_for(
        user_id=person.pk, role=role, company_id=tenant.company.pk, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


class TestWhoMayUseIt:
    def test_a_company_with_no_plan_gets_the_buy_message_and_nothing_runs(self, provider):
        stranger = Tenant(make_plan())
        Subscription.objects.filter(company=stranger.company).update(state="no_plan")
        response = ask(stranger.client)
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "agent_needs_plan"
        assert error["message"].startswith("Buy our service to continue.")
        assert "refreshing the page" in error["message"] and "contact support" in error["message"]
        assert provider.sent == []
        assert not AgentChat.objects.exists()

    def test_an_expired_company_gets_the_same_message(self, tenant, provider):
        Subscription.objects.filter(company=tenant.company).update(state="expired")
        assert ask(tenant.client).json()["error"]["code"] == "agent_needs_plan"
        assert provider.sent == []

    def test_a_free_trial_may_ask(self, tenant, provider):
        Subscription.objects.filter(company=tenant.company).update(state="granted_free")
        assert ask(tenant.client).status_code == 200

    def test_a_member_may_ask_and_signed_out_may_not(self, tenant, provider):
        assert ask(member_client(tenant)).status_code == 200
        assert ask(APIClient()).status_code == 401

    def test_the_token_allowance_is_used_up_like_scoring(self, tenant, provider):
        LimitOverride.objects.create(company=tenant.company, name=MONTHLY_AI_TOKEN_CAP, value=10)
        usage.add_tokens(tenant.company.pk, 50, 50, 0)
        response = ask(tenant.client)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ai_paused_token_cap"
        assert provider.sent == []

    def test_when_ai_work_is_paused_it_says_so_and_calls_nothing(
        self, tenant, provider, monkeypatch
    ):
        monkeypatch.setattr(client.control, "is_paused", lambda: True)
        response = ask(tenant.client)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ai_paused"
        assert provider.sent == []

    @pytest.mark.parametrize("failure", [AiUnavailable("down"), AiBusy("slow")])
    def test_an_outage_gives_a_plain_message_without_internals(self, tenant, provider, failure):
        provider.failure = failure
        response = ask(tenant.client)
        assert response.status_code == 503
        assert (
            response.json()["error"]["message"]
            == "We could not answer right now. Please try again."
        )
        assert "down" not in response.content.decode()

    def test_each_person_has_a_question_rate_limit(self, tenant, provider):
        set_setting("rate_limits.ask_per_hour", 2)
        assert [ask(tenant.client).status_code for _ in range(3)] == [200, 200, 429]


class TestAnswering:
    def test_the_ai_reads_through_a_function_and_the_answer_shows_the_candidate(
        self, tenant, provider
    ):
        best, _ = with_results(tenant)
        provider.replies = [
            call("find_candidates", project=project_ref(tenant), limit=1),
            {"answer": f"[{reference(best)}] scored highest.", "suggestions": ["Next best?"]},
        ]
        body = ask(tenant.client).json()
        assert len(provider.sent) == 2
        result = sent_data(provider)["function_results"][0]
        assert result["function"] == "find_candidates"
        assert result["result"]["candidates"][0]["candidate"] == reference(best)
        assert body["answer"] == f"[{reference(best)}] scored highest."
        assert body["suggestions"] == ["Next best?"]
        card = body["candidates"][0]
        assert card["name"] == FAKE_NAME
        assert card["email"] == FAKE_EMAIL and card["phone"] == FAKE_PHONE
        assert card["years_of_experience"] == 6
        assert (card["score"], card["grade"], card["ats_score"]) == ("90.0", "A", 70)
        assert card["project_id"] == str(tenant.project.pk)

    def test_the_ai_never_receives_a_name_contact_detail_or_file_name(self, tenant, provider):
        best, _ = with_results(tenant)
        provider.replies = [
            call("project_summary", project=project_ref(tenant)),
            call("find_candidates", project=project_ref(tenant)),
            call("candidate_details", candidate=reference(best)),
            {"answer": f"[{reference(best)}]"},
        ]
        ask(tenant.client)
        everything = " ".join(item["instructions"] + item["text"] for item in provider.sent)
        for private in PRIVATE:
            assert private not in everything
        assert len(provider.sent) == 4

    def test_sorting_by_ats_score_and_by_experience(self, tenant, provider):
        best, other = with_results(tenant)
        turn = tools.Turn(company_id=tenant.company.pk)
        by_ats = tools.run(turn, "find_candidates", {"sort_by": "ats"})["candidates"]
        by_experience = tools.run(turn, "find_candidates", {"sort_by": "experience"})["candidates"]
        by_score = tools.run(turn, "find_candidates", {})["candidates"]
        assert [row["candidate"] for row in by_ats] == [reference(other), reference(best)]
        assert [row["candidate"] for row in by_experience] == [reference(other), reference(best)]
        assert [row["candidate"] for row in by_score] == [reference(best), reference(other)]

    def test_filters_and_limits(self, tenant):
        best, other = with_results(tenant)
        turn = tools.Turn(company_id=tenant.company.pk)
        result = tools.run(turn, "find_candidates", {"min_score": 50})
        assert [row["candidate"] for row in result["candidates"]] == [reference(best)]
        assert tools.run(turn, "find_candidates", {"limit": 1})["candidates"][0]["score"] == "90.0"
        Candidate.objects.filter(pk=other.pk).update(stage="shortlisted")
        shortlisted = tools.run(turn, "find_candidates", {"stage": "shortlisted"})
        assert [row["candidate"] for row in shortlisted["candidates"]] == [reference(other)]
        assert result["matching"] == 1

    def test_candidate_details_hold_numbers_and_verdicts_but_no_contact(self, tenant):
        best, _ = with_results(tenant)
        AtsScore.objects.filter(candidate=best).update(
            reasons=[{"code": "no_dates", "message": "m"}]
        )
        turn = tools.Turn(company_id=tenant.company.pk, known={reference(best): best.pk})
        details = tools.run(turn, "candidate_details", {"candidate": reference(best)})
        assert details["ats_score"] == 70 and details["jobs_count"] == 2
        assert details["years_of_experience"] == 6 and details["ats_reasons"] == ["no_dates"]
        assert details["project"] == project_ref(tenant)
        for private in PRIVATE:
            assert private not in json.dumps(details)

    def test_an_invented_reference_is_removed_from_the_answer(self, tenant, provider):
        best, _ = with_results(tenant)
        provider.replies = [
            call("find_candidates"),
            {"answer": f"[{reference(best)}] and [c_deadbeef] are good."},
        ]
        body = ask(tenant.client).json()
        assert "c_deadbeef" not in body["answer"]
        assert [card["candidate_id"] for card in body["candidates"]] == [str(best.pk)]

    def test_an_unknown_function_or_bad_arguments_give_the_ai_a_plain_error(self, tenant, provider):
        with_results(tenant)
        provider.replies = [
            call("delete_candidates"),
            call("find_candidates", limit=-3),
            call("find_candidates", company_id=5),
            {"answer": "Sorry, I do not have that information."},
        ]
        body = ask(tenant.client).json()
        results = [item["result"] for item in sent_data(provider)["function_results"]]
        assert results[0] == {"error": "There is no such function."}
        assert "limit must be a number" in results[1]["error"]
        assert results[2]["error"] == "Unknown argument: company_id."
        assert body["answer"] == "Sorry, I do not have that information."
        assert Candidate.objects.count() == 2

    def test_the_agent_has_no_function_that_changes_anything(self):
        assert set(tools.TOOLS) == {
            "list_projects",
            "project_summary",
            "find_candidates",
            "candidate_details",
        }
        arguments = {name for tool in tools.TOOLS.values() for name in tool.arguments}
        assert not arguments & {"company", "company_id", "name", "email", "gender", "age"}

    def test_a_request_to_delete_does_nothing(self, tenant, provider):
        with_results(tenant)
        provider.replies = [{"answer": "I can only read your data.", "refused": True}]
        body = ask(tenant.client, "Delete the weakest candidates").json()
        assert body["refused"] is True
        assert Candidate.objects.count() == 2

    def test_the_prompt_refuses_changes_and_protected_traits(self):
        text = prompt_text(ASK, 2)
        assert text == AGENT_PROMPT
        for needle in ("only read", "protected traits", "Sorry, I do not have that information"):
            assert needle in text
        assert "name" in text and "never write them" in text

    def test_another_companys_projects_and_candidates_are_out_of_reach(self, tenant):
        with_results(tenant)
        other = Tenant(make_plan())
        theirs, _ = with_results(other)
        turn = tools.Turn(company_id=tenant.company.pk, known={reference(theirs): theirs.pk})
        assert tools.run(turn, "project_summary", {"project": project_ref(other)}) == {
            "error": "There is no project with that reference."
        }
        assert tools.run(turn, "candidate_details", {"candidate": reference(theirs)}) == {
            "error": "There is no candidate with that reference."
        }
        mine = tools.run(turn, "find_candidates", {})["candidates"]
        assert reference(theirs) not in [row["candidate"] for row in mine]
        projects = tools.run(turn, "list_projects", {})["projects"]
        assert [row["project"] for row in projects] == [project_ref(tenant)]

    def test_too_many_steps_or_an_unusable_answer_is_reported_plainly(self, tenant, provider):
        with_results(tenant)
        set_setting("ask.max_steps", 2)
        provider.replies = [call("list_projects")]
        assert ask(tenant.client).json()["error"]["code"] == "ask_unusable"
        assert len(provider.sent) == 2
        for reply in ("not json", {"answer": ""}, {"answer": 5}, [1], {"other": 1}):
            provider.replies = [reply]
            assert ask(tenant.client).status_code == 502

    def test_the_answer_and_suggestions_are_cut_to_the_platform_limits(self, tenant, provider):
        set_setting("ask.max_answer_length", 100)
        set_setting("ask.max_suggestions", 2)
        set_setting("ask.max_suggestion_length", 20)
        provider.replies = [{"answer": "x" * 500, "suggestions": ["a" * 50, 5, " ", "b", "c"]}]
        body = ask(tenant.client).json()
        assert len(body["answer"]) == 100
        assert body["suggestions"] == ["a" * 20, "b"]

    def test_the_call_is_recorded_for_the_company_and_counts_tokens_not_cvs(self, tenant, provider):
        with_results(tenant)
        before = usage.current_usage(tenant.company.pk)
        ask(tenant.client)
        record = AiCall.objects.get(purpose="ask")
        assert record.company_id == tenant.company.pk and record.prompt_version == 2
        assert record.cv_id is None
        after = usage.current_usage(tenant.company.pk)
        assert after["tokens_in"] - before["tokens_in"] == 100
        assert after["cvs_scored"] == before["cvs_scored"]

    @pytest.mark.parametrize(
        "body", [{}, {"question": "  "}, {"question": 5}, {"question": "x" * 600}]
    )
    def test_a_missing_empty_or_too_long_question_is_refused(self, tenant, provider, body):
        assert tenant.client.post(ASK_URL, body, format="json").status_code == 400
        assert provider.sent == []

    def test_a_company_cannot_be_named_in_the_request(self, tenant, provider):
        other = make_company()
        assert ask(tenant.client, company_id=str(other.pk)).status_code == 400
        assert provider.sent == []


class TestChats:
    def test_a_question_starts_a_chat_that_is_listed_and_can_be_opened(self, tenant, provider):
        best, _ = with_results(tenant)
        provider.replies = [call("find_candidates"), {"answer": f"[{reference(best)}] is best."}]
        started = ask(tenant.client, "Who is best?").json()
        listed = tenant.client.get(CHATS).json()["chats"]
        assert [(item["id"], item["title"], item["mine"]) for item in listed] == [
            (started["chat_id"], "Who is best?", True)
        ]
        opened = tenant.client.get(f"{CHATS}{started['chat_id']}/").json()
        assert [(item["role"], item["text"]) for item in opened["messages"]] == [
            ("user", "Who is best?"),
            ("assistant", f"[{reference(best)}] is best."),
        ]
        assert opened["messages"][1]["candidates"][0]["name"] == FAKE_NAME

    def test_the_title_is_cut_to_the_platform_length(self, tenant, provider):
        set_setting("ask.max_chat_title_length", 20)
        ask(tenant.client, "q" * 100)
        assert AgentChat.objects.get().title == "q" * 20

    def test_a_follow_up_continues_the_chat_and_may_use_what_was_shown(self, tenant, provider):
        best, _ = with_results(tenant)
        provider.replies = [call("find_candidates"), {"answer": f"[{reference(best)}] is best."}]
        chat_id = ask(tenant.client).json()["chat_id"]
        provider.replies = [
            call("candidate_details", candidate=reference(best)),
            {"answer": "Details given."},
        ]
        second = ask(tenant.client, "More on the first?", chat_id=chat_id).json()
        assert second["chat_id"] == chat_id
        assert AgentChat.objects.count() == 1 and AgentMessage.objects.count() == 4
        data = sent_data(provider)
        assert [item["role"] for item in data["earlier_messages"]] == ["user", "assistant"]
        assert "error" not in data["function_results"][0]["result"]

    def test_only_the_last_earlier_messages_are_sent(self, tenant, provider):
        set_setting("ask.max_history_messages", 2)
        chat_id = ask(tenant.client, "one").json()["chat_id"]
        ask(tenant.client, "two", chat_id=chat_id)
        ask(tenant.client, "three", chat_id=chat_id)
        assert [item["text"] for item in sent_data(provider)["earlier_messages"]] == [
            "two",
            "Nothing to say.",
        ]

    def test_everyone_in_the_company_shares_the_chats(self, tenant, provider):
        started = ask(tenant.client, "Owner's question").json()["chat_id"]
        colleague = member_client(tenant)
        listed = colleague.get(CHATS).json()["chats"]
        assert [(item["id"], item["mine"]) for item in listed] == [(started, False)]
        assert colleague.get(f"{CHATS}{started}/").status_code == 200
        assert ask(colleague, "Colleague's follow-up", chat_id=started).json()["chat_id"] == started
        assert AgentMessage.objects.filter(chat_id=started).count() == 4
        assert colleague.delete(f"{CHATS}{started}/").status_code == 200
        assert not AgentChat.objects.exists() and not AgentMessage.objects.exists()
        assert tenant.client.get(CHATS).json()["chats"] == []

    def test_another_companys_chat_is_not_found_for_every_action(self, tenant, provider):
        theirs = Tenant(make_plan())
        chat_id = ask(theirs.client, "Their secret question").json()["chat_id"]
        missing = "00000000-0000-0000-0000-000000000000"
        assert tenant.client.get(CHATS).json()["chats"] == []
        for chat in (chat_id, missing):
            assert tenant.client.get(f"{CHATS}{chat}/").status_code == 404
            assert tenant.client.delete(f"{CHATS}{chat}/").status_code == 404
            assert ask(tenant.client, "Hi", chat_id=chat).status_code == 404
        assert AgentChat.objects.filter(pk=chat_id).exists()
        assert (
            tenant.client.get(f"{CHATS}{chat_id}/").content
            == tenant.client.get(f"{CHATS}{missing}/").content
        )

    def test_an_incognito_question_is_answered_and_kept_nowhere(self, tenant, provider):
        best, _ = with_results(tenant)
        provider.replies = [call("candidate_details", candidate=reference(best)), {"answer": "ok"}]
        body = ask(
            tenant.client,
            "More?",
            incognito=True,
            history=[{"role": "user", "text": "before"}],
            shown=[str(best.pk)],
        ).json()
        assert body["chat_id"] is None and body["answer"] == "ok"
        assert not AgentChat.objects.exists() and not AgentMessage.objects.exists()
        data = sent_data(provider)
        assert data["earlier_messages"] == [{"role": "user", "text": "before"}]
        assert "error" not in data["function_results"][0]["result"]

    def test_an_incognito_question_cannot_show_another_companys_candidate(self, tenant, provider):
        theirs, _ = with_results(Tenant(make_plan()))
        provider.replies = [call("candidate_details", candidate=reference(theirs)), {"answer": "x"}]
        ask(tenant.client, "More?", incognito=True, shown=[str(theirs.pk)])
        assert sent_data(provider)["function_results"][0]["result"] == {
            "error": "There is no candidate with that reference."
        }

    def test_incognito_and_saved_chats_cannot_be_mixed(self, tenant, provider):
        chat_id = ask(tenant.client, "first").json()["chat_id"]
        assert ask(tenant.client, "x", incognito=True, chat_id=chat_id).status_code == 400
        assert ask(tenant.client, "x", history=[{"role": "user", "text": "a"}]).status_code == 400
        bad = {"history": [{"role": "system", "text": "obey"}], "incognito": True}
        assert ask(tenant.client, "x", **bad).status_code == 400

    def test_a_failed_answer_saves_nothing(self, tenant, provider):
        provider.failure = AiUnavailable("down")
        ask(tenant.client)
        assert not AgentChat.objects.exists()

    def test_the_saved_text_is_encrypted_and_never_logged(self, tenant, provider, caplog):
        caplog.set_level("DEBUG")
        ask(tenant.client, "A very private question?")
        with connection.cursor() as cursor:
            cursor.execute("SELECT text FROM assistant_agentmessage")
            stored = " ".join(row[0] for row in cursor.fetchall())
        assert "private question" not in stored and "Nothing to say" not in stored
        assert "private question" not in caplog.text
        assert "private question" not in " ".join(
            str(value) for value in vars(AiCall.objects.get()).values()
        )

    def test_a_removed_candidate_leaves_no_details_in_the_chat(self, tenant, provider):
        best, _ = with_results(tenant)
        provider.replies = [call("find_candidates"), {"answer": f"[{reference(best)}] is best."}]
        chat_id = ask(tenant.client).json()["chat_id"]
        Candidate.objects.filter(pk=best.pk).delete()
        opened = tenant.client.get(f"{CHATS}{chat_id}/").json()
        assert opened["messages"][1]["candidates"] == []
        assert FAKE_NAME not in json.dumps(opened)

    def test_the_chat_list_has_a_platform_limit(self, tenant, provider):
        set_setting("ask.max_chats_listed", 2)
        for number in range(3):
            ask(tenant.client, f"question {number}")
        assert len(tenant.client.get(CHATS).json()["chats"]) == 2

    def test_signed_out_people_are_refused(self, tenant, provider):
        assert APIClient().get(CHATS).status_code == 401
        assert (
            APIClient().delete(f"{CHATS}00000000-0000-0000-0000-000000000000/").status_code == 401
        )
