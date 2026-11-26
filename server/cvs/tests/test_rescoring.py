import pytest

from ai.client import AiUnavailable
from ai.models import AiCall
from cvs import candidates, evaluation, processing, rescoring, scoring
from cvs.models import CandidateScore, CvFile, RequirementResult
from cvs.tests.test_ai_reading import StubAi, set_setting
from cvs.tests.test_candidate_record import add_profile, make_cv
from cvs.tests.test_requirement_evaluation import (
    CV_TEXT,
    PYTHON,
    TEAM,
    add_requirements,
    answer,
    entry,
)
from projects.models import Requirement
from projects.requirements import list_requirements, save_requirements
from projects.scoring_settings import save_scoring_settings
from usage import service as usage

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai(monkeypatch):
    return StubAi(monkeypatch)


@pytest.fixture(autouse=True)
def steps(monkeypatch):
    """Only the steps re-scoring needs; the text step hands over a ready, guarded CV text."""
    real = dict(processing.STEPS)
    processing.STEPS.clear()
    processing.STEPS["text_reading"] = lambda context: context.state.update(
        text=CV_TEXT, scoring_text=CV_TEXT
    )
    processing.STEPS["requirement_evaluation"] = evaluation.evaluate_the_requirements
    processing.STEPS["scoring"] = scoring.calculate_the_score
    kicks = []
    monkeypatch.setattr(processing, "async_task", lambda job: kicks.append(job))
    monkeypatch.setattr(
        rescoring, "kick", lambda count: kicks.extend([processing.TICK_JOB] * count)
    )
    yield kicks
    processing.STEPS.clear()
    processing.STEPS.update(real)


@pytest.fixture
def kicks(steps):
    return steps


@pytest.fixture
def scored(ai):
    """A finished, scored CV: Python met, team partly met, AWS missing (must-haves, weight 3)."""
    cv = add_profile(make_cv())
    add_requirements(cv.project, "Python experience", "Team leadership", "AWS certification")
    candidate = candidates.create_candidate(cv)
    ai.answers = [
        answer(entry(1, "met", PYTHON), entry(2, "partly_met", TEAM), entry(3, "missing"))
    ]
    evaluation.evaluate_candidate(candidate, CV_TEXT)
    scoring.score_candidate(candidate)
    CvFile.objects.filter(pk=cv.pk).update(status="done")
    usage.mark_scored(cv.company_id, cv.pk)
    ai.calls.clear()
    AiCall.objects.all().delete()
    return candidate


def edit(candidate, changes=None, add=(), ack=True):
    """Saves the project's requirements with the changes: {position: new text or a dict of
    fields}, plus new items to add."""
    changes = changes or {}
    project = candidate.project
    items = []
    for position, row in enumerate(list_requirements(project)):
        row = {k: row[k] for k in ("id", "kind", "text", "weight")}
        change = changes.get(position)
        if isinstance(change, dict):
            row.update(change)
        elif change is not None:
            row["text"] = change
        items.append(row)
    items += list(add)
    return save_requirements(project.pk, project.company_id, items, acknowledge_rescoring=ack)


def score_of(candidate):
    return CandidateScore.objects.get(candidate=candidate)


class TestWeightsNeedNoAi:
    def test_a_weight_change_recalculates_at_once_and_runs_nothing(self, scored, ai, kicks):
        before = score_of(scored).score  # (100 + 50 + 0) / 3 = 50
        edit(scored, {0: {"weight": 1}})
        assert ai.calls == [] and kicks == []
        stored = score_of(scored)
        assert stored.score != before and stored.outdated is False
        assert CvFile.objects.get(pk=scored.cv_file_id).status == "done"

    def test_a_threshold_change_recalculates_the_label_with_no_ai(self, scored, ai, kicks):
        save_scoring_settings(
            scored.project.pk, scored.company_id,
            {"must_weight_percent": 70, "nice_weight_percent": 30, "recommendation_threshold": 40,
             "top_n": 10, "cap_on_missing_must_have": False},
        )  # fmt: skip
        assert score_of(scored).label == "strong_match"
        assert ai.calls == [] and kicks == []

    def test_removing_a_requirement_needs_no_ai_and_rescores_at_once(self, scored, ai, kicks):
        project = scored.project
        rows = [r for r in list_requirements(project) if r["text"] != "AWS certification"]
        items = [{k: r[k] for k in ("id", "kind", "text", "weight")} for r in rows]
        save_requirements(project.pk, project.company_id, items)
        assert ai.calls == [] and kicks == []
        assert float(score_of(scored).score) == 75.0  # (100 + 50) / 2


class TestOnlyTheChangedRequirementRuns:
    def test_the_saved_change_marks_the_score_outdated_and_queues_the_cv(self, scored, kicks):
        edit(scored, {1: "Leading engineering teams"})
        assert score_of(scored).outdated is True
        assert CvFile.objects.get(pk=scored.cv_file_id).status == "waiting"
        assert kicks == [processing.TICK_JOB]

    def test_only_the_changed_requirement_is_sent_to_the_ai(self, scored, ai):
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        assert len(ai.calls) == 1
        sent = ai.calls[0]["text"]
        assert "Leading engineering teams" in sent
        assert "Python experience" not in sent and "AWS certification" not in sent

    def test_the_other_results_are_kept_and_the_new_one_replaces_the_old(self, scored, ai):
        python_before = RequirementResult.objects.get(
            candidate=scored, requirement_text="Python experience"
        )
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        found = {
            r.requirement_text: r.verdict
            for r in RequirementResult.objects.filter(candidate=scored)
        }
        assert found == {
            "Python experience": "met",
            "Leading engineering teams": "met",
            "AWS certification": "missing",
        }
        assert (
            RequirementResult.objects.get(pk=python_before.pk).created_at
            == python_before.created_at
        )

    def test_the_score_is_new_and_no_longer_outdated(self, scored, ai):
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        stored = score_of(scored)
        assert (float(stored.score), stored.outdated) == (66.7, False)  # (100 + 100 + 0) / 3
        assert CvFile.objects.get(pk=scored.cv_file_id).status == "done"

    def test_a_new_requirement_is_judged_on_the_existing_cv(self, scored, ai):
        edit(scored, add=[{"kind": "nice", "text": "Kubernetes", "weight": 2}])
        ai.answers = [answer(entry(1, "missing"))]
        processing.tick()
        assert len(ai.calls) == 1 and "Kubernetes" in ai.calls[0]["text"]
        assert RequirementResult.objects.filter(candidate=scored).count() == 4
        assert score_of(scored).outdated is False

    def test_the_call_is_recorded_for_the_candidate(self, scored, ai):
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        row = AiCall.objects.get()
        assert (row.purpose, row.candidate_id, row.result) == ("scoring", scored.pk, "ok")

    def test_the_profile_is_not_read_again(self, scored, ai):
        profile_id = scored.profile_id
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        assert scored.__class__.objects.get(pk=scored.pk).profile_id == profile_id
        assert all("Requirements" in call["text"] for call in ai.calls)  # no reading call

    def test_a_second_change_before_the_first_ran_still_judges_only_what_is_new(self, scored, ai):
        edit(scored, {1: "Leading engineering teams"})
        edit(scored, {0: "Python and Django"})
        ai.answers = [answer(entry(1, "met", PYTHON), entry(2, "met", TEAM))]
        processing.tick()
        assert len(ai.calls) == 1 and "AWS certification" not in ai.calls[0]["text"]

    def test_re_scoring_never_counts_the_cv_again(self, scored, ai):
        before = usage.current_usage(scored.company_id)["cvs_scored"]
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        assert usage.current_usage(scored.company_id)["cvs_scored"] == before
        assert usage.waiting_cvs(scored.company_id) == 0

    def test_its_tokens_count_for_the_company(self, scored, ai):
        before = usage.current_usage(scored.company_id)["tokens_in"]
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        assert usage.current_usage(scored.company_id)["tokens_in"] == before + 100


class TestAPartialFailure:
    @pytest.fixture(autouse=True)
    def one_try(self):
        set_setting("processing.max_attempts", 1)

    def test_a_failed_ai_call_leaves_the_old_score_marked_outdated(self, scored, ai):
        old = score_of(scored)
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [AiUnavailable("Timeout")]
        processing.tick()
        cv = CvFile.objects.get(pk=scored.cv_file_id)
        assert (cv.status, cv.failure_reason != "") == ("failed", True)
        stored = score_of(scored)
        assert (stored.score, stored.grade, stored.outdated) == (old.score, old.grade, True)

    def test_the_failed_call_is_recorded(self, scored, ai):
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [AiUnavailable("Timeout")]
        processing.tick()
        assert AiCall.objects.get().result == "failed"

    def test_a_failed_re_scoring_does_not_take_the_cv_back_out_of_the_count(self, scored, ai):
        before = usage.current_usage(scored.company_id)["cvs_scored"]
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [AiUnavailable("Timeout")]
        processing.tick()
        assert usage.current_usage(scored.company_id)["cvs_scored"] == before

    def test_retrying_finishes_the_job_even_when_the_months_limit_is_used_up(self, scored, ai):
        from plans.models import Plan

        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [AiUnavailable("Timeout")]
        processing.tick()
        Plan.objects.update(cvs_per_month=1)  # the month is full: the CV is already counted
        processing.retry_failed(CvFile.objects.get(pk=scored.cv_file_id))
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        assert score_of(scored).outdated is False

    def test_one_cv_failing_does_not_stop_the_others(self, scored, ai):
        second_cv = add_profile(make_cv(company=scored.company, project=scored.project))
        other = candidates.create_candidate(second_cv)
        ai.answers = [answer(entry(1, "met", PYTHON), entry(2, "met", TEAM), entry(3, "missing"))]
        evaluation.evaluate_candidate(other, CV_TEXT)
        scoring.score_candidate(other)
        CvFile.objects.filter(pk=second_cv.pk).update(status="done")
        usage.mark_scored(second_cv.company_id, second_cv.pk)
        edit(scored, {1: "Leading engineering teams"})
        ai.answers = [AiUnavailable("Timeout"), answer(entry(1, "met", TEAM))]
        processing.tick()
        processing.tick()
        statuses = sorted(CvFile.objects.values_list("status", flat=True))
        assert statuses == ["done", "failed"]


class TestWhatTheUserSeesFirst:
    def test_the_change_asks_first_with_the_cvs_requirements_and_cost(self, scored):
        from core.errors import AppError

        with pytest.raises(AppError) as asked:
            edit(scored, {1: "Leading engineering teams"}, ack=False)
        assert asked.value.code == "rescoring_needed"
        details = asked.value.details
        assert (details["cvs"], details["requirements"]) == (1, 1)
        assert "estimated_cost" in details
        assert Requirement.objects.filter(text="Leading engineering teams").count() == 0
        assert CandidateScore.objects.get(candidate=scored).outdated is False

    def test_a_weight_change_never_asks(self, scored):
        edit(scored, {0: {"weight": 5}}, ack=False)

    def test_the_estimate_grows_with_cvs_and_changed_requirements(self, scored):
        project = scored.project
        rows = list_requirements(project)
        items = [{k: r[k] for k in ("id", "kind", "text", "weight")} for r in rows]
        one = rescoring.estimate(project, [{**items[0], "text": "New one"}, *items[1:]])
        two = rescoring.estimate(
            project, [{**items[0], "text": "New one"}, {**items[1], "text": "New two"}, items[2]]
        )
        assert (one["requirements"], two["requirements"]) == (1, 2)
        assert two["tokens_total"] > one["tokens_total"] > 0
        assert two["estimated_cost"] >= one["estimated_cost"]
        assert one["approximate"] is True

    def test_nothing_to_rescore_means_no_cvs_and_no_cost(self, scored):
        project = scored.project
        rows = list_requirements(project)
        items = [{k: r[k] for k in ("id", "kind", "text", "weight")} for r in rows]
        shown = rescoring.estimate(project, items)
        assert (shown["cvs"], shown["tokens_total"], shown["blocked"]) == (0, 0, False)

    def test_unscored_cvs_are_not_counted(self, scored):
        second = candidates.create_candidate(
            add_profile(make_cv(company=scored.company, project=scored.project))
        )
        project = scored.project
        items = [
            {k: r[k] for k in ("id", "kind", "text", "weight")} for r in list_requirements(project)
        ]
        shown = rescoring.estimate(project, [{**items[0], "text": "New"}, *items[1:]])
        assert shown["cvs"] == 1 and second.pk != scored.pk


class TestOutdatedShowsInTheApi:
    def test_the_recommendation_says_outdated_until_judged_again(self, scored, ai):
        from rest_framework.test import APIClient

        from core.tests.factories import start_session_for

        issued = start_session_for(
            user_id=scored.project.created_by_id, role="owner",
            company_id=scored.company_id, kind="company",
        )  # fmt: skip
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        url = f"/api/company/projects/{scored.project.pk}/candidates/{scored.pk}/recommendation/"
        assert client.get(url).json()["outdated"] is False
        edit(scored, {1: "Leading engineering teams"})
        assert client.get(url).json()["outdated"] is True
        ai.answers = [answer(entry(1, "met", TEAM))]
        processing.tick()
        assert client.get(url).json()["outdated"] is False
