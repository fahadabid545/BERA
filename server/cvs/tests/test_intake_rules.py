import pytest

from cvs import candidates, scoring
from cvs.models import Candidate, RequirementResult, StageChange
from cvs.stages import AUTOMATIC_NAME, history
from cvs.tests.test_candidate_record import add_profile, make_cv
from cvs.tests.test_requirement_evaluation import add_requirements
from projects.models import Project, ProjectScoringSettings

pytestmark = pytest.mark.django_db


def judged_candidate(verdict, **project_fields):
    """A candidate whose single must-have was judged `verdict`: met scores 100, partly met 50,
    missing 0. The project's rules are set before the first score is worked out."""
    cv = add_profile(make_cv())
    Project.objects.filter(pk=cv.project_id).update(**project_fields)
    (requirement,) = add_requirements(cv.project, "Python experience")
    candidate = candidates.create_candidate(cv)
    RequirementResult.objects.create(
        company_id=cv.company_id, candidate=candidate, requirement=requirement,
        requirement_text=requirement.text, verdict=verdict,
        evidence="" if verdict == "missing" else "Python", confidence="high",
        model="m", prompt_version=1,
    )  # fmt: skip
    return candidate


def stage_of(candidate):
    return Candidate.objects.get(pk=candidate.pk).stage


class TestAutoShortlist:
    def test_a_strong_first_score_starts_shortlisted(self):
        candidate = judged_candidate("met", auto_shortlist=True)
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "shortlisted"

    def test_a_score_below_the_strong_match_threshold_stays_new(self):
        candidate = judged_candidate("partly_met", auto_shortlist=True)
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "new"

    def test_the_rule_is_off_by_default(self):
        candidate = judged_candidate("met")
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "new"
        assert not StageChange.objects.exists()

    def test_the_projects_own_threshold_is_used(self):
        candidate = judged_candidate("partly_met", auto_shortlist=True)
        ProjectScoringSettings.objects.create(
            project=candidate.project, company_id=candidate.company_id,
            must_weight_percent=100, nice_weight_percent=0, recommendation_threshold=40, top_n=5,
            cap_on_missing_must_have=False,
        )  # fmt: skip
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "shortlisted"


class TestAutoReject:
    def test_a_score_under_the_limit_goes_straight_to_rejected(self):
        candidate = judged_candidate("missing", auto_reject_below=30)
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "rejected"

    def test_a_score_at_the_limit_is_kept(self):
        candidate = judged_candidate("partly_met", auto_reject_below=50)
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "new"

    def test_a_limit_of_zero_rejects_nobody(self):
        candidate = judged_candidate("missing", auto_reject_below=0)
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "new"

    def test_rejecting_wins_when_both_rules_apply(self):
        candidate = judged_candidate("met", auto_shortlist=True, auto_reject_below=101)
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "rejected"


class TestHistoryAndOneTimeOnly:
    def test_the_move_is_in_the_history_as_a_project_rule(self):
        candidate = judged_candidate("met", auto_shortlist=True)
        scoring.score_candidate(candidate)
        (entry,) = history(candidate)
        assert (entry["from_stage"], entry["to_stage"], entry["by"]) == (
            "new", "shortlisted", AUTOMATIC_NAME,
        )  # fmt: skip

    def test_scoring_again_never_undoes_a_decision_by_hand(self):
        candidate = judged_candidate("met", auto_shortlist=True)
        scoring.score_candidate(candidate)
        Candidate.objects.filter(pk=candidate.pk).update(stage="new")
        scoring.score_candidate(candidate)  # a later re-score is not a first score
        assert stage_of(candidate) == "new"
        assert StageChange.objects.count() == 1

    def test_a_candidate_a_person_already_moved_is_left_alone(self):
        candidate = judged_candidate("met", auto_shortlist=True)
        Candidate.objects.filter(pk=candidate.pk).update(stage="on_hold")
        candidate.refresh_from_db()
        scoring.score_candidate(candidate)
        assert stage_of(candidate) == "on_hold"
