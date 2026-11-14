import json
import logging

import pytest
from django.db import IntegrityError, transaction

from ai.client import AiUnavailable
from ai.prompt_versions import SCORING, prompt_text
from cvs import candidates, evaluation, processing
from cvs.models import CvFile, RequirementResult
from cvs.processing import PermanentFailure
from cvs.tests.test_ai_reading import StubAi, set_setting
from cvs.tests.test_candidate_record import add_profile, make_cv
from projects import deletion
from projects.models import Requirement
from usage import service as usage

pytestmark = pytest.mark.django_db

CV_TEXT = (
    "Senior Backend Engineer at Acme for six years.\n"
    "Built services in Python and Django.\n"
    "Led a team of five engineers.\n"
    "BSc in Computer Science."
)
PYTHON = "Built services in Python and Django."
TEAM = "Led a team of five engineers."


@pytest.fixture
def ai(monkeypatch):
    return StubAi(monkeypatch)


def entry(number, verdict="met", evidence="", confidence="high", **extra):
    return {
        "requirement": number,
        "verdict": verdict,
        "evidence": evidence,
        "confidence": confidence,
        **extra,
    }


def answer(*entries):
    return json.dumps({"results": list(entries)})


def add_requirements(project, *texts):
    return [
        Requirement.objects.create(
            company_id=project.company_id,
            project=project,
            position=position,
            kind="must",
            text=text,
            weight=3,
        )
        for position, text in enumerate(texts, 1)
    ]


@pytest.fixture
def candidate():
    cv = add_profile(make_cv())
    add_requirements(cv.project, "Python experience", "Team leadership", "AWS certification")
    return candidates.create_candidate(cv)


def results_of(candidate):
    return {
        result.requirement.text: result
        for result in RequirementResult.objects.filter(candidate=candidate)
    }


class TestResultsFollowTheShape:
    def test_each_requirement_gets_a_verdict_a_quote_and_a_confidence(self, candidate, ai):
        ai.answers = [
            answer(
                entry(1, "met", PYTHON, "high"),
                entry(2, "partly_met", "Led a team of five", "medium"),
                entry(3, "missing", "", "low"),
            )
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        found = results_of(candidate)
        python, team, aws = (
            found["Python experience"],
            found["Team leadership"],
            found["AWS certification"],
        )
        assert (python.verdict, python.evidence, python.confidence) == ("met", PYTHON, "high")
        assert (team.verdict, team.evidence, team.confidence) == (
            "partly_met",
            "Led a team of five",
            "medium",
        )
        assert (aws.verdict, aws.evidence, aws.confidence) == ("missing", "", "low")

    def test_one_call_covers_every_requirement_and_uses_the_pinned_model_and_prompt(
        self, candidate, ai
    ):
        ai.answers = [answer(entry(1, "missing"), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1
        call = ai.calls[0]
        project = candidate.project
        assert call["model"] == project.scoring_model
        assert call["instructions"] == prompt_text(SCORING, project.scoring_prompt_version)
        assert "1. Python experience\n2. Team leadership\n3. AWS certification" in call["text"]
        assert CV_TEXT in call["text"]

    def test_the_result_records_the_model_and_prompt_version_it_was_made_with(self, candidate, ai):
        ai.answers = [answer(entry(1, "missing"), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        result = RequirementResult.objects.first()
        assert result.model == candidate.project.scoring_model
        assert result.prompt_version == candidate.project.scoring_prompt_version
        assert result.company_id == candidate.company_id

    def test_tokens_are_counted_for_the_cvs_company(self, candidate, ai):
        ai.answers = [answer(entry(1, "missing"), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert usage.current_usage(candidate.company_id)["tokens_in"] == 100


class TestQuotesMustReallyExist:
    def test_an_invented_quote_is_discarded_and_only_that_requirement_is_asked_again(
        self, candidate, ai
    ):
        ai.answers = [
            answer(
                entry(1, "met", PYTHON),
                entry(2, "met", "Managed a department of fifty people."),
                entry(3, "missing"),
            ),
            answer(entry(2, "met", TEAM, "medium")),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2
        second = ai.calls[1]["text"]
        assert "2. Team leadership" in second
        assert "Python experience" not in second and "AWS certification" not in second
        found = results_of(candidate)
        assert found["Team leadership"].evidence == TEAM
        assert found["Python experience"].evidence == PYTHON

    def test_a_quote_that_is_still_invented_after_the_retry_means_missing(self, candidate, ai):
        invented = "Managed a department of fifty people."
        ai.answers = [
            answer(entry(1, "met", PYTHON), entry(2, "met", invented), entry(3, "missing")),
            answer(entry(2, "met", invented)),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2
        team = results_of(candidate)["Team leadership"]
        assert (team.verdict, team.evidence, team.confidence) == ("missing", "", "low")
        assert RequirementResult.objects.count() == 3

    def test_there_is_only_one_retry(self, candidate, ai):
        invented = "Not in the CV at all."
        ai.answers = [
            answer(entry(1, "met", invented), entry(2, "met", invented), entry(3, "met", invented)),
            answer(entry(1, "met", invented), entry(2, "met", invented), entry(3, "met", invented)),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2
        assert {r.verdict for r in RequirementResult.objects.all()} == {"missing"}

    def test_the_number_of_retries_is_a_platform_setting(self, candidate, ai):
        set_setting("ai.invalid_answer_retries", 0)
        ai.answers = [
            answer(entry(1, "met", "Invented."), entry(2, "missing"), entry(3, "missing"))
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1
        assert results_of(candidate)["Python experience"].verdict == "missing"

    def test_a_quote_is_found_whatever_the_case_spacing_or_line_breaks(self, candidate, ai):
        ai.answers = [
            answer(
                entry(1, "met", "built SERVICES  in python\nand django."),
                entry(2, "met", "Led a team of  five engineers."),
                entry(3, "missing"),
            )
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1
        assert results_of(candidate)["Python experience"].verdict == "met"

    def test_a_quote_with_one_word_changed_is_rejected(self, candidate, ai):
        ai.answers = [
            answer(
                entry(1, "met", "Built services in Java and Django."),
                entry(2, "met", TEAM),
                entry(3, "missing"),
            ),
            answer(entry(1, "missing")),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2
        assert results_of(candidate)["Python experience"].verdict == "missing"

    def test_a_quote_longer_than_the_limit_is_rejected_even_when_it_is_real(self, candidate, ai):
        set_setting("evaluation.evidence_max_length", 20)
        ai.answers = [
            answer(
                entry(1, "met", PYTHON), entry(2, "met", "Led a team of five"), entry(3, "missing")
            ),
            answer(entry(1, "met", "Built services")),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2
        assert results_of(candidate)["Python experience"].evidence == "Built services"

    def test_a_quote_of_exactly_the_limit_is_accepted(self, candidate, ai):
        quote = PYTHON[:200]
        set_setting("evaluation.evidence_max_length", len(quote))
        ai.answers = [answer(entry(1, "met", quote), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1

    def test_the_default_limit_is_two_hundred_characters(self, candidate, ai):
        long_cv = "Python " * 60  # a real quote of 419 characters
        ai.answers = [
            answer(entry(1, "met", long_cv.strip()), entry(2, "missing"), entry(3, "missing")),
            answer(entry(1, "missing")),
        ]
        evaluation.evaluate_candidate(candidate, long_cv)
        assert len(ai.calls) == 2

    def test_no_evidence_means_missing_without_asking_again(self, candidate, ai):
        ai.answers = [
            answer(
                entry(1, "met", "", "high"),
                entry(2, "partly_met", "  ", "medium"),
                entry(3, "missing"),
            )
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1
        found = results_of(candidate)
        assert (found["Python experience"].verdict, found["Python experience"].evidence) == (
            "missing",
            "",
        )
        assert found["Team leadership"].verdict == "missing"

    def test_a_missing_verdict_keeps_no_quote(self, candidate, ai):
        ai.answers = [answer(entry(1, "missing", PYTHON), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert results_of(candidate)["Python experience"].evidence == ""

    def test_a_missing_verdict_needs_no_evidence_field_at_all(self, candidate, ai):
        ai.answers = [
            json.dumps(
                {
                    "results": [
                        {"requirement": n, "verdict": "missing", "confidence": "low"}
                        for n in (1, 2, 3)
                    ]
                }
            )
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1 and RequirementResult.objects.count() == 3


class TestOtherInvalidResults:
    @pytest.mark.parametrize(
        "bad",
        [
            entry(1, "excellent", PYTHON),
            entry(1, "met", PYTHON, "certain"),
            entry(1, "met", 42),
            entry(1, "met", None),
            {"requirement": 1, "verdict": "met", "confidence": "high"},
            "not an object",
        ],
    )
    def test_an_entry_with_a_wrong_value_is_asked_again(self, candidate, ai, bad):
        ai.answers = [
            answer(bad, entry(2, "missing"), entry(3, "missing")),
            answer(entry(1, "met", PYTHON)),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2
        assert results_of(candidate)["Python experience"].verdict == "met"

    def test_a_requirement_the_answer_leaves_out_is_asked_again(self, candidate, ai):
        ai.answers = [
            answer(entry(1, "missing"), entry(2, "missing")),
            answer(entry(3, "missing")),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2 and RequirementResult.objects.count() == 3

    def test_entries_for_unknown_numbers_are_ignored_and_the_first_of_a_repeat_wins(
        self, candidate, ai
    ):
        ai.answers = [
            answer(
                entry(1, "met", PYTHON),
                entry(1, "missing"),
                entry(9, "met", TEAM),
                entry(True, "met", TEAM),
                entry(2, "missing"),
                entry(3, "missing"),
            )
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1 and RequirementResult.objects.count() == 3
        assert results_of(candidate)["Python experience"].verdict == "met"

    @pytest.mark.parametrize("bad", ["not json", "[]", "{}", json.dumps({"results": "x"})])
    def test_an_unusable_answer_is_asked_for_again_in_full(self, candidate, ai, bad):
        ai.answers = [bad, answer(entry(1, "missing"), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2 and RequirementResult.objects.count() == 3
        assert "1. Python experience" in ai.calls[1]["text"]
        assert "3. AWS certification" in ai.calls[1]["text"]

    def test_two_unusable_answers_fail_the_cv_with_a_reason_and_save_nothing(self, candidate, ai):
        ai.answers = ["nope", "still nope"]
        with pytest.raises(PermanentFailure) as failure:
            evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert str(failure.value) == evaluation.UNUSABLE_REASON
        assert not RequirementResult.objects.exists()
        assert usage.current_usage(candidate.company_id)["tokens_in"] == 200

    def test_an_unavailable_ai_is_left_to_the_processing_retries(self, candidate, ai):
        ai.answers = [AiUnavailable("down")]
        with pytest.raises(AiUnavailable):
            evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert not RequirementResult.objects.exists()

    def test_a_company_over_its_token_cap_is_not_judged_and_the_reason_is_clear(self, ai):
        cv = add_profile(make_cv())
        from cvs.tests.test_ai_reading import make_cv as make_capped_cv

        capped = add_profile(make_capped_cv(cap=10))
        add_requirements(capped.project, "Python experience")
        usage.add_tokens(capped.company_id, 10, 0, 0)
        with pytest.raises(PermanentFailure) as failure:
            evaluation.evaluate_candidate(candidates.create_candidate(capped), CV_TEXT)
        assert str(failure.value) == evaluation.AI_PAUSED_REASON and not ai.calls
        assert cv


class TestNeedsRequirements:
    def test_a_project_with_none_fails_the_cv_with_a_clear_reason_and_asks_nothing(self, ai):
        candidate = candidates.create_candidate(add_profile(make_cv()))
        with pytest.raises(PermanentFailure) as failure:
            evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert "requirement" in str(failure.value).lower() and not ai.calls


class TestResultsAreReused:
    def test_a_cv_already_judged_is_not_sent_to_the_ai_again(self, candidate, ai):
        ai.answers = [answer(entry(1, "missing"), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 1 and RequirementResult.objects.count() == 3

    def test_only_a_new_requirement_is_judged(self, candidate, ai):
        ai.answers = [
            answer(entry(1, "met", PYTHON), entry(2, "missing"), entry(3, "missing")),
            answer(entry(1, "met", TEAM)),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        add_requirements_after = Requirement.objects.create(
            company_id=candidate.company_id,
            project=candidate.project,
            position=9,
            kind="nice",
            text="Leads teams",
            weight=2,
        )
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2
        assert (
            "1. Leads teams" in ai.calls[1]["text"]
            and "Python experience" not in ai.calls[1]["text"]
        )
        assert RequirementResult.objects.filter(requirement=add_requirements_after).exists()
        assert results_of(candidate)["Python experience"].evidence == PYTHON

    def test_an_edited_requirement_is_judged_again_and_the_others_are_not(self, candidate, ai):
        ai.answers = [
            answer(entry(1, "met", PYTHON), entry(2, "missing"), entry(3, "missing")),
            answer(entry(1, "missing")),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        Requirement.objects.filter(project=candidate.project, text="Python experience").update(
            text="Rust experience"
        )
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        assert len(ai.calls) == 2 and "1. Rust experience" in ai.calls[1]["text"]
        assert results_of(candidate)["Rust experience"].verdict == "missing"
        assert RequirementResult.objects.count() == 3


class TestAsAStep:
    @pytest.fixture(autouse=True)
    def only_the_step(self):
        real = dict(processing.STEPS)
        processing.STEPS.clear()
        processing.register_step("requirement_evaluation", evaluation.evaluate_the_requirements)
        yield
        processing.STEPS.clear()
        processing.STEPS.update(real)

    def run(self, candidate, state):
        cv = CvFile.objects.get(pk=candidate.cv_file_id)
        context = processing.StepContext(cv, cv.company_id, cv.project_id, state)
        evaluation.evaluate_the_requirements(context)

    def test_the_step_is_plugged_into_its_slot_after_the_candidate_record(self):
        assert processing.STEPS["requirement_evaluation"] is evaluation.evaluate_the_requirements
        slots = processing.SLOTS
        assert slots.index("candidate_record") < slots.index("requirement_evaluation")
        assert slots.index("requirement_evaluation") < slots.index("scoring")

    def test_the_step_judges_the_guarded_text_and_never_the_original(self, candidate, ai):
        ai.answers = [answer(entry(1, "missing"), entry(2, "missing"), entry(3, "missing"))]
        self.run(
            candidate,
            {"text": "Jane Example jane@example.com\n" + CV_TEXT, "scoring_text": CV_TEXT},
        )
        assert "Jane" not in ai.calls[0]["text"] and "jane@" not in ai.calls[0]["text"]
        assert CV_TEXT in ai.calls[0]["text"]

    def test_a_quote_from_the_removed_personal_details_is_not_accepted(self, candidate, ai):
        ai.answers = [
            answer(entry(1, "met", "jane@example.com"), entry(2, "missing"), entry(3, "missing")),
            answer(entry(1, "missing")),
        ]
        self.run(
            candidate,
            {"text": "jane@example.com\n" + CV_TEXT, "scoring_text": CV_TEXT},
        )
        assert results_of(candidate)["Python experience"].verdict == "missing"

    def test_a_cv_goes_through_the_slot_to_done(self, candidate, ai):
        ai.answers = [answer(entry(1, "met", PYTHON), entry(2, "missing"), entry(3, "missing"))]
        row = CvFile.objects.get(pk=candidate.cv_file_id)
        row.claim_token = "11111111-1111-1111-1111-111111111111"
        row.status = "reading"
        row.save()
        processing.STEPS["text_reading"] = lambda c: c.state.update(
            text=CV_TEXT, scoring_text=CV_TEXT
        )
        processing.run_item(CvFile.objects.get(pk=row.pk))
        assert CvFile.objects.get(pk=row.pk).status == "done"
        assert RequirementResult.objects.count() == 3

    def test_a_cv_with_no_requirements_fails_with_the_reason(self, ai):
        candidate = candidates.create_candidate(add_profile(make_cv()))
        row = CvFile.objects.get(pk=candidate.cv_file_id)
        row.claim_token = "11111111-1111-1111-1111-111111111111"
        row.save()
        processing.STEPS["text_reading"] = lambda c: c.state.update(
            text=CV_TEXT, scoring_text=CV_TEXT
        )
        processing.run_item(CvFile.objects.get(pk=row.pk))
        failed = CvFile.objects.get(pk=row.pk)
        assert failed.status == "failed" and "requirement" in failed.failure_reason.lower()


class TestLogs:
    def test_nothing_from_the_cv_or_the_answer_is_logged(self, candidate, ai, caplog):
        caplog.set_level(logging.DEBUG)
        ai.answers = [
            "Led a team of five engineers",
            answer(entry(1, "met", TEAM), entry(2, "missing"), entry(3, "missing")),
        ]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        for line in caplog.text.splitlines():
            assert "five engineers" not in line and "Python" not in line


class TestStorageRules:
    def test_a_missing_result_with_a_quote_is_refused_by_the_database(self, candidate):
        requirement = Requirement.objects.filter(project=candidate.project).first()
        with pytest.raises(IntegrityError), transaction.atomic():
            RequirementResult.objects.create(
                company_id=candidate.company_id,
                candidate=candidate,
                requirement=requirement,
                requirement_text=requirement.text,
                verdict="missing",
                evidence="a quote",
                confidence="low",
                model="m",
                prompt_version=1,
            )

    def test_a_met_result_without_a_quote_is_refused_by_the_database(self, candidate):
        requirement = Requirement.objects.filter(project=candidate.project).first()
        with pytest.raises(IntegrityError), transaction.atomic():
            RequirementResult.objects.create(
                company_id=candidate.company_id,
                candidate=candidate,
                requirement=requirement,
                requirement_text=requirement.text,
                verdict="met",
                evidence="",
                confidence="high",
                model="m",
                prompt_version=1,
            )

    def test_one_result_per_candidate_and_requirement(self, candidate, ai):
        ai.answers = [answer(entry(1, "missing"), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)
        first = RequirementResult.objects.first()
        with pytest.raises(IntegrityError), transaction.atomic():
            RequirementResult.objects.create(
                company_id=candidate.company_id,
                candidate=candidate,
                requirement=first.requirement,
                requirement_text="x",
                verdict="missing",
                confidence="low",
                model="m",
                prompt_version=1,
            )


class TestRemoval:
    def judged(self, candidate, ai):
        ai.answers = [answer(entry(1, "met", PYTHON), entry(2, "missing"), entry(3, "missing"))]
        evaluation.evaluate_candidate(candidate, CV_TEXT)

    def test_removing_the_candidate_removes_its_results(self, candidate, ai):
        self.judged(candidate, ai)
        candidates.remove_candidate(candidate)
        assert not RequirementResult.objects.exists()

    def test_deleting_the_project_removes_the_results(self, candidate, ai):
        self.judged(candidate, ai)
        deletion.delete_project(candidate.cv_file.uploaded_by, candidate.project)
        assert not RequirementResult.objects.exists()

    def test_removing_a_requirement_removes_its_results_only(self, candidate, ai):
        self.judged(candidate, ai)
        Requirement.objects.get(project=candidate.project, text="Team leadership").delete()
        assert RequirementResult.objects.count() == 2


class TestAnotherCompany:
    def test_results_belong_to_the_candidates_company_and_are_removed_with_its_project_only(
        self, ai
    ):
        mine = candidates.create_candidate(add_profile(make_cv()))
        theirs = candidates.create_candidate(add_profile(make_cv()))
        for one in (mine, theirs):
            add_requirements(one.project, "Python experience")
        ai.answers = [answer(entry(1, "met", PYTHON)), answer(entry(1, "missing"))]
        evaluation.evaluate_candidate(mine, CV_TEXT)
        evaluation.evaluate_candidate(theirs, CV_TEXT)
        assert RequirementResult.objects.get(candidate=mine).company_id == mine.company_id
        assert RequirementResult.objects.filter(company_id=mine.company_id).count() == 1
        deletion.delete_project(mine.cv_file.uploaded_by, mine.project)
        assert RequirementResult.objects.get().company_id == theirs.company_id
