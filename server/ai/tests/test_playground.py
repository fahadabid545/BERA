import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction

from ai import client, control, playground
from ai.client import AiAnswer, AiUnavailable
from ai.models import AiCall, AiModel, PromptVersion
from ai.tests.test_model_settings import REASON, admin_client
from audit.models import AuditEvent
from core.tests.factories import make_admin_user, make_company, make_company_user
from cvs.models import (
    Candidate,
    CandidateScore,
    CvContact,
    CvFile,
    CvProfile,
    RequirementResult,
)
from cvs.tests.files import make_pdf
from cvs.tests.test_ai_reading import set_setting
from projects.models import Project, Requirement
from usage.models import UsageCounter

pytestmark = pytest.mark.django_db
OPTIONS = "/api/admin/ai/playground/"
RUN = "/api/admin/ai/playground/run/"
EMAIL = "jane@example.com"
CV_LINE = f"Jane Example {EMAIL} Backend Engineer 2018 present Python Django PostgreSQL"
JOB = "We need a backend engineer who knows Python. Kubernetes is a plus."

PROFILE = {
    "contact": {"name": "Jane Example", "email": EMAIL, "phone": "", "address": ""},
    "skills": ["Python", "Django"],
    "jobs": [{"title": "Backend Engineer", "start": "2018", "end": "present"}],
    "years_of_experience": 8,
    "education": [],
    "certifications": [],
    "languages": [],
    "summary": "A backend engineer who builds services in Python.",
}
REQUIREMENTS = {
    "language": "en",
    "requirements": [
        {"kind": "must", "text": "Python experience"},
        {"kind": "nice", "text": "Kubernetes"},
    ],
}
JUDGEMENTS = {
    "results": [
        {"requirement": 1, "verdict": "met", "evidence": "Python Django", "confidence": "high"},
        {"requirement": 2, "verdict": "missing", "evidence": "", "confidence": "medium"},
    ]
}
# (answer, tokens in, tokens out) of the three steps, in the order a run asks for them.
READING_ANSWER = (json.dumps(PROFILE), 1000, 500)
REQUIREMENTS_ANSWER = (json.dumps(REQUIREMENTS), 200, 100)
JUDGEMENT_ANSWER = (json.dumps(JUDGEMENTS), 400, 200)
GOOD_RUN = [READING_ANSWER, REQUIREMENTS_ANSWER, JUDGEMENT_ANSWER]
# Prices per million tokens of the two test models, so every cost below is exact.
READING_COST = Decimal("0.007000")  # 1000 x 2 + 500 x 10, per million
REQUIREMENTS_COST = Decimal("0.001400")
JUDGEMENT_COST = Decimal("0.002800")  # 400 x 3 + 200 x 8, per million
TOTAL_COST = Decimal("0.011200")


class StubAi:
    """Replaces the one place that talks to the provider; answers in order."""

    def __init__(self, monkeypatch):
        self.answers, self.calls = [], []
        monkeypatch.setattr(client, "_send", self._send)

    def _send(self, **call):
        self.calls.append(call)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        text, tokens_in, tokens_out = answer
        return AiAnswer(text=text, tokens_in=tokens_in, tokens_out=tokens_out)


@pytest.fixture
def ai(monkeypatch):
    return StubAi(monkeypatch)


@pytest.fixture
def boss():
    return admin_client("super")[0]


@pytest.fixture(autouse=True)
def models_and_prompts():
    AiModel.objects.create(
        name="read-model", input_price_per_million=2, output_price_per_million=10
    )
    AiModel.objects.create(
        name="score-model", input_price_per_million=3, output_price_per_million=8
    )
    AiModel.objects.create(
        name="off-model", input_price_per_million=1, output_price_per_million=1, enabled=False
    )
    PromptVersion.objects.get_or_create(kind="reading", number=2, defaults={"text": "Reading two."})
    PromptVersion.objects.get_or_create(kind="scoring", number=2, defaults={"text": "Scoring two."})


def pdf(text=CV_LINE):
    return SimpleUploadedFile("cv.pdf", make_pdf(text=text), content_type="application/pdf")


def body(**changes):
    values = {
        "cv_file": pdf(),
        "job_description": JOB,
        "reading_model": "read-model",
        "scoring_model": "score-model",
        "reading_prompt_version": 2,
        "scoring_prompt_version": 2,
        **changes,
    }
    return {name: value for name, value in values.items() if value is not None}


def run(boss, **changes):
    return boss.post(RUN, body(**changes), format="multipart")


def play_spend(amount, when=None):
    call = AiCall.objects.create(
        purpose="playground", model="read-model", duration_ms=1, result="ok",
        estimated_cost=Decimal(amount),
    )  # fmt: skip
    if when:
        AiCall.objects.filter(pk=call.pk).update(created_at=when)


class TestAFullRun:
    def test_shows_the_profile_requirement_results_score_tokens_and_cost(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        reply = run(boss)
        assert reply.status_code == 200, reply.content
        shown = reply.json()
        assert shown["profile"]["skills"] == ["Python", "Django"]
        assert shown["profile"]["jobs"][0]["title"] == "Backend Engineer"
        assert shown["requirements"] == [
            {
                "kind": "must", "text": "Python experience", "weight": 3, "verdict": "met",
                "evidence": "Python Django", "confidence": "high",
            },
            {
                "kind": "nice", "text": "Kubernetes", "weight": 3, "verdict": "missing",
                "evidence": "", "confidence": "medium",
            },
        ]  # fmt: skip
        score = shown["score"]
        assert (score["score"], score["must_score"], score["nice_score"]) == (
            "70.0",
            "100.0",
            "0.0",
        )
        assert score["grade"] in "ABCDE" and score["label"] and score["guide_note"]
        assert score["strengths"] and score["risks"] and score["interview_questions"]
        usage = shown["usage"]
        assert [step["step"] for step in usage["steps"]] == [
            "reading", "requirement_extraction", "scoring",
        ]  # fmt: skip
        assert [(step["tokens_in"], step["tokens_out"]) for step in usage["steps"]] == [
            (1000, 500), (200, 100), (400, 200),
        ]  # fmt: skip
        assert [Decimal(step["cost"]) for step in usage["steps"]] == [
            READING_COST, REQUIREMENTS_COST, JUDGEMENT_COST,
        ]  # fmt: skip
        assert (usage["tokens_in"], usage["tokens_out"]) == (1600, 800)
        assert Decimal(usage["cost"]) == TOTAL_COST

    def test_the_choices_decide_what_the_ai_is_sent(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        run(boss)
        reading, extraction, scoring = ai.calls
        assert (reading["model"], reading["instructions"]) == ("read-model", "Reading two.")
        assert extraction["model"] == "read-model"
        assert (scoring["model"], scoring["instructions"]) == ("score-model", "Scoring two.")

    def test_scoring_never_sees_the_personal_details(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        run(boss)
        reading, _, scoring = ai.calls
        assert EMAIL in reading["text"]
        assert EMAIL not in scoring["text"]
        assert "Python Django" in scoring["text"]

    def test_the_contact_details_are_not_in_the_answer(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        assert EMAIL not in run(boss).content.decode()

    def test_a_cv_notice_is_passed_on(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        set_setting("uploads.cv_pages_read", 1)
        sent = SimpleUploadedFile("cv.pdf", make_pdf(pages=2, text=CV_LINE))
        assert "Only the first 1 are read" in run(boss, cv_file=sent).json()["notice"]


class TestNothingIsSavedToAnyCompany:
    def test_a_run_writes_no_company_data(self, boss, ai):
        make_company()  # an existing company must not be touched either
        ai.answers = list(GOOD_RUN)
        tables = (
            Project, Requirement, CvFile, CvProfile, CvContact, Candidate, RequirementResult,
            CandidateScore, UsageCounter,
        )  # fmt: skip
        before = [table.objects.count() for table in tables]
        assert run(boss).status_code == 200
        assert [table.objects.count() for table in tables] == before

    def test_the_calls_are_recorded_as_playground_for_no_company(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        run(boss)
        calls = AiCall.objects.order_by("created_at", "pk")
        assert calls.count() == 3
        assert {(call.purpose, call.company_id) for call in calls} == {("playground", None)}
        assert [call.estimated_cost for call in calls] == [
            READING_COST, REQUIREMENTS_COST, JUDGEMENT_COST,
        ]  # fmt: skip
        assert {call.project_id for call in calls} == {None}

    def test_the_database_keeps_playground_calls_out_of_companies(self):
        def record(company, purpose):
            with transaction.atomic():
                AiCall.objects.create(
                    company=company, purpose=purpose, model="m", duration_ms=1, result="ok"
                )

        with pytest.raises(IntegrityError):
            record(make_company(), "playground")
        with pytest.raises(IntegrityError):
            record(None, "scoring")

    def test_company_calls_still_need_a_company(self, monkeypatch):
        StubAi(monkeypatch).answers = [("{}", 1, 1)]
        with pytest.raises(IntegrityError), transaction.atomic():
            client.call_ai(None, purpose="scoring", model="m", instructions="i", text="t")


class TestTheChoices:
    def test_a_model_that_is_off_or_unknown_is_refused(self, boss, ai):
        for field in ("reading_model", "scoring_model"):
            for name in ("off-model", "no-such-model"):
                reply = run(boss, **{field: name})
                assert reply.status_code == 400
                assert (
                    reply.json()["error"]["fields"][field] == "Choose a model that is switched on."
                )
        assert ai.calls == []

    def test_a_prompt_version_that_does_not_exist_is_refused(self, boss, ai):
        for field in ("reading_prompt_version", "scoring_prompt_version"):
            reply = run(boss, **{field: 99})
            assert reply.status_code == 400
            assert reply.json()["error"]["fields"][field] == "There is no such version."
        assert ai.calls == []

    def test_a_version_of_the_other_kind_is_not_taken_for_it(self, boss, ai):
        PromptVersion.objects.create(kind="scoring", number=9, text="Only scoring.")
        assert run(boss, reading_prompt_version=9).status_code == 400
        assert ai.calls == []

    @pytest.mark.parametrize(
        "field",
        [
            "cv_file", "job_description", "reading_model", "scoring_model",
            "reading_prompt_version", "scoring_prompt_version",
        ],
    )  # fmt: skip
    def test_every_choice_is_needed(self, boss, ai, field):
        reply = run(boss, **{field: None, "cv_file": None if field == "cv_file" else pdf()})
        assert reply.status_code == 400
        assert field in reply.json()["error"]["fields"]
        assert ai.calls == []

    def test_a_blank_job_description_is_refused(self, boss, ai):
        assert run(boss, job_description="   ").status_code == 400
        assert ai.calls == []

    def test_a_job_description_over_the_limit_is_refused(self, boss, ai):
        set_setting("projects.description_max_length", 500)
        assert run(boss, job_description="x" * 501).status_code == 400
        assert ai.calls == []


class TestTheCvFile:
    def test_a_file_that_is_not_a_pdf_or_word_file_is_refused(self, boss, ai):
        sent = SimpleUploadedFile("cv.txt", b"plain text of a cv, long enough to read")
        reply = run(boss, cv_file=sent)
        assert reply.status_code == 400 and "cv_file" in reply.json()["error"]["fields"]
        assert ai.calls == []

    def test_an_empty_file_is_refused(self, boss, ai):
        reply = run(boss, cv_file=SimpleUploadedFile("cv.pdf", b""))
        assert reply.status_code == 400 and "cv_file" in reply.json()["error"]["fields"]
        assert ai.calls == []

    def test_a_damaged_file_is_refused(self, boss, ai):
        reply = run(boss, cv_file=SimpleUploadedFile("cv.pdf", b"%PDF-1.4 not really"))
        assert reply.status_code == 400 and "cv_file" in reply.json()["error"]["fields"]
        assert ai.calls == []

    def test_a_file_that_is_too_large_is_refused(self, boss, ai):
        set_setting("uploads.max_file_size_mb", 1)
        reply = run(boss, cv_file=SimpleUploadedFile("cv.pdf", b"0" * (1024 * 1024 + 1)))
        assert reply.status_code == 413 and reply.json()["error"]["code"] == "request_too_large"
        assert ai.calls == []


class TestWhenTheAiCannotHelp:
    def test_an_unavailable_ai_gives_a_plain_message_and_keeps_what_was_counted(self, boss, ai):
        ai.answers = [READING_ANSWER, AiUnavailable("OpenAIError details")]
        reply = run(boss)
        assert reply.status_code == 503
        assert reply.json()["error"]["message"] == "The AI could not answer. Try again later."
        assert "OpenAIError" not in reply.content.decode()
        calls = AiCall.objects.order_by("created_at", "pk")
        assert [call.result for call in calls] == ["ok", "failed"]
        assert [call.estimated_cost for call in calls] == [READING_COST, 0]
        assert playground.budget()["spent"] == "0.007000"

    def test_a_paused_ai_is_refused_before_any_call(self, boss, ai):
        control.pause(make_admin_user(email="pauser@example.test"), REASON)
        reply = run(boss)
        assert reply.status_code == 503 and reply.json()["error"]["code"] == "ai_paused"
        assert ai.calls == []

    def test_an_answer_that_cannot_be_used_is_asked_for_again_then_refused(self, boss, ai):
        ai.answers = [("not json", 10, 5), ("still not json", 10, 5)]
        reply = run(boss)
        assert reply.status_code == 422
        assert reply.json()["error"]["code"] == "playground_unusable_answer"
        assert len(ai.calls) == 2

    def test_a_job_description_with_no_requirements_is_reported(self, boss, ai):
        ai.answers = [READING_ANSWER, ("not json", 10, 5)]
        reply = run(boss)
        assert reply.status_code == 422
        assert reply.json()["error"]["code"] == "playground_no_requirements"
        assert (
            reply.json()["error"]["message"]
            == "No requirements could be found in this job description."
        )

    def test_a_failed_run_lets_the_next_one_start(self, boss, ai):
        ai.answers = [AiUnavailable("down")]
        assert run(boss).status_code == 503
        ai.answers = list(GOOD_RUN)
        assert run(boss).status_code == 200


class TestTheTestBudget:
    def test_the_page_shows_the_limit_spent_and_remaining(self, boss):
        play_spend("2.5")
        shown = boss.get(OPTIONS).json()["budget"]
        assert (shown["limit"], shown["spent"], shown["remaining"]) == (
            "10.000000", "2.500000", "7.500000",
        )  # fmt: skip
        assert shown["used_up"] is False

    def test_the_limit_is_the_platform_setting(self, boss):
        set_setting("ai.playground_monthly_budget_usd", 3)
        assert boss.get(OPTIONS).json()["budget"]["limit"] == "3.000000"

    def test_a_run_adds_its_cost_to_what_was_spent(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        shown = run(boss).json()["budget"]
        assert Decimal(shown["spent"]) == TOTAL_COST
        assert Decimal(shown["remaining"]) == Decimal("10") - TOTAL_COST

    def test_a_run_is_refused_once_the_budget_is_used_up(self, boss, ai):
        play_spend("10")
        reply = run(boss)
        assert reply.status_code == 409
        assert reply.json()["error"]["code"] == "playground_budget_used_up"
        assert reply.json()["error"]["message"] == "The test budget for this month is used up."
        assert ai.calls == []

    def test_spending_just_under_the_limit_still_allows_a_run(self, boss, ai):
        play_spend("9.99")
        ai.answers = list(GOOD_RUN)
        assert run(boss).status_code == 200

    def test_a_run_stops_before_a_call_that_would_start_over_the_limit(self, boss, ai):
        set_setting("ai.playground_monthly_budget_usd", 0.005)
        ai.answers = [READING_ANSWER, REQUIREMENTS_ANSWER, JUDGEMENT_ANSWER]
        reply = run(boss)
        assert (
            reply.status_code == 409
            and reply.json()["error"]["code"] == "playground_budget_used_up"
        )
        assert len(ai.calls) == 1  # the reading call went through, nothing after it
        assert AiCall.objects.count() == 1

    def test_only_test_runs_count_against_the_test_budget(self, boss):
        company = make_company()
        AiCall.objects.create(
            company=company, purpose="scoring", model="m", duration_ms=1, result="ok",
            estimated_cost=Decimal("500"),
        )  # fmt: skip
        assert boss.get(OPTIONS).json()["budget"]["spent"] == "0.000000"

    def test_test_runs_do_not_count_toward_any_company(self, boss, ai):
        company = make_company()
        ai.answers = list(GOOD_RUN)
        run(boss)
        assert AiCall.objects.filter(company=company).count() == 0
        assert UsageCounter.objects.count() == 0

    def test_the_budget_starts_again_each_utc_month(self, boss):
        play_spend("9", when=datetime(2026, 10, 31, 23, 59, tzinfo=UTC))
        play_spend("1", when=datetime(2026, 11, 1, 0, 0, tzinfo=UTC))
        shown = playground.budget(datetime(2026, 11, 15, 12, 0, tzinfo=UTC))
        assert (shown["month"], shown["spent"]) == ("2026-11", "1.000000")

    def test_the_remaining_budget_is_never_below_zero(self, boss):
        play_spend("12")
        shown = boss.get(OPTIONS).json()["budget"]
        assert shown["remaining"] == "0.000000" and shown["used_up"] is True


class TestTwoRunsAtOnce:
    def hold_the_lock(self):
        other = connection.copy()
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [playground.RUN_LOCK_NUMBER])
        return other

    def test_a_run_is_refused_while_another_is_in_progress(self, boss, ai):
        other = self.hold_the_lock()
        try:
            reply = run(boss)
        finally:
            other.close()  # closing the connection lets go of its lock
        assert reply.status_code == 409 and reply.json()["error"]["code"] == "playground_busy"
        assert (
            reply.json()["error"]["message"]
            == "Another test run is in progress. Try again in a moment."
        )
        assert ai.calls == []

    def test_the_lock_is_let_go_after_a_run(self, boss, ai):
        ai.answers = list(GOOD_RUN)
        assert run(boss).status_code == 200
        other = self.hold_the_lock()  # would wait forever if the run still held it
        other.close()

    def test_the_budget_is_checked_after_the_lock_is_won(self, boss, ai, monkeypatch):
        """A run that waited for the lock sees what the run before it spent."""
        order = []
        real_budget = playground._check_budget
        monkeypatch.setattr(
            playground,
            "_check_budget",
            lambda: (order.append(lock_is_held()), real_budget())[1],
        )
        ai.answers = list(GOOD_RUN)
        run(boss)
        assert order and all(order)


class TestOnlySuperAdmins:
    def test_support_is_refused_everywhere(self, ai):
        support = admin_client("support")[0]
        assert support.get(OPTIONS).status_code == 403
        assert support.put(OPTIONS, {"monthly_budget": 5, "reason": REASON}).status_code == 403
        assert run(support).status_code == 403
        assert ai.calls == []

    def test_a_company_user_is_refused(self, ai):
        from rest_framework.test import APIClient

        from signin import service

        person = make_company_user(make_company())
        issued = service.start_session(
            user_id=person.pk, role="owner", company_id=person.company_id, kind="company"
        )
        member = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert member.get(OPTIONS).status_code in (401, 403)
        assert run(member).status_code in (401, 403)
        assert ai.calls == []

    def test_someone_not_signed_in_is_refused(self, ai):
        from rest_framework.test import APIClient

        assert APIClient().get(OPTIONS).status_code == 401
        assert APIClient().post(RUN, body(), format="multipart").status_code == 401
        assert ai.calls == []


class TestOptions:
    def test_lists_the_models_that_are_on_and_the_prompt_versions(self, boss):
        shown = boss.get(OPTIONS).json()
        assert "read-model" in shown["models"] and "score-model" in shown["models"]
        assert "off-model" not in shown["models"]
        assert shown["prompts"]["reading"] == [
            {"number": 1, "current": True},
            {"number": 2, "current": False},
        ]
        assert [item["number"] for item in shown["prompts"]["scoring"]] == [1, 2]


class TestChangingTheBudget:
    def test_a_super_admin_changes_it_with_a_reason_and_it_is_audited(self, boss):
        reply = boss.put(OPTIONS, {"monthly_budget": "25.50", "reason": REASON}, format="json")
        assert reply.status_code == 200
        assert reply.json()["limit"] == "25.500000"
        assert boss.get(OPTIONS).json()["budget"]["limit"] == "25.500000"
        event = AuditEvent.objects.get(kind="admin.ai_playground_budget_changed")
        assert event.reason == REASON
        assert event.details["changes"]["monthly_budget"] == {"old": "10", "new": "25.50"}

    def test_a_reason_is_needed(self, boss):
        reply = boss.put(OPTIONS, {"monthly_budget": 5, "reason": " "}, format="json")
        assert reply.status_code == 400
        assert AuditEvent.objects.count() == 0

    @pytest.mark.parametrize("value", [0, -1, "abc", None, "0.001"])
    def test_a_budget_that_is_not_above_zero_dollars_is_refused(self, boss, value):
        reply = boss.put(OPTIONS, {"monthly_budget": value, "reason": REASON}, format="json")
        assert reply.status_code == 400
        assert boss.get(OPTIONS).json()["budget"]["limit"] == "10.000000"

    def test_lowering_it_below_what_was_spent_refuses_runs(self, boss, ai):
        play_spend("4")
        boss.put(OPTIONS, {"monthly_budget": 4, "reason": REASON}, format="json")
        assert run(boss).status_code == 409
        assert ai.calls == []


def lock_is_held():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND objid = %s"
            " AND pid = pg_backend_pid()",
            [playground.RUN_LOCK_NUMBER],
        )
        return cursor.fetchone()[0] > 0
