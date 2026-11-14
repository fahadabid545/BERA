from decimal import Decimal

import pytest

from ai import client
from cvs import candidates, processing, scoring
from cvs.models import CandidateScore, RequirementResult
from cvs.processing import PermanentFailure
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_candidate_record import add_profile, make_cv
from projects import scoring_settings
from projects.models import ProjectScoringSettings, Requirement
from projects.requirements import list_requirements, save_requirements

pytestmark = pytest.mark.django_db

D = Decimal
MET, PARTLY, MISSING = "met", "partly_met", "missing"
SPLIT = (D(70), D(30))


def combine(entries, split=SPLIT, cap=False):
    return scoring.combine(entries, *split, cap)


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    """Scoring is the system's own logic: any AI call here is a failure."""

    def refuse(**call):
        raise AssertionError("the AI must not be called to calculate a score")

    monkeypatch.setattr(client, "_send", refuse)


class TestWorkedExamples:
    def test_everything_met_is_100_and_grade_a(self):
        outcome = combine([("must", 3, MET), ("nice", 1, MET)])
        assert (outcome.score, outcome.grade) == (D("100.0"), "A")

    def test_everything_missing_is_0_and_grade_e(self):
        outcome = combine([("must", 3, MISSING), ("nice", 1, MISSING)])
        assert (outcome.score, outcome.grade) == (D("0.0"), "E")

    def test_the_verdicts_count_100_50_and_0(self):
        assert combine([("must", 1, MET)]).score == D("100.0")
        assert combine([("must", 1, PARTLY)]).score == D("50.0")
        assert combine([("must", 1, MISSING)]).score == D("0.0")

    def test_weights_inside_a_group_and_the_70_30_split(self):
        # must: (3*100 + 1*0) / 4 = 75; nice: 50; 75*0.7 + 50*0.3 = 67.5
        outcome = combine([("must", 3, MET), ("must", 1, MISSING), ("nice", 1, PARTLY)])
        assert (outcome.score, outcome.grade) == (D("67.5"), "C")
        assert (outcome.must_score, outcome.nice_score) == (D("75.0"), D("50.0"))

    def test_a_heavier_requirement_moves_the_score_more(self):
        light = combine([("must", 1, MET), ("must", 4, MISSING)]).score
        heavy = combine([("must", 4, MET), ("must", 1, MISSING)]).score
        assert (light, heavy) == (D("20.0"), D("80.0"))  # one group: its weights alone decide

    def test_another_split_is_used(self):
        entries = [("must", 1, MET), ("nice", 1, MISSING)]
        assert combine(entries, (D(50), D(50))).score == D("50.0")
        assert combine(entries, (D(100), D(0))).score == D("100.0")

    def test_the_same_inputs_always_give_the_same_score(self):
        entries = [("must", 2, PARTLY), ("must", 3, MET), ("nice", 7, MISSING), ("nice", 1, MET)]
        assert len({combine(list(reversed(entries))).score for _ in range(5)}) == 1
        assert combine(entries) == combine(list(reversed(entries)))


class TestOneGroup:
    def test_only_must_haves_can_still_reach_100(self):
        assert combine([("must", 1, MET), ("must", 2, MET)]).score == D("100.0")

    def test_only_nice_to_haves_can_still_reach_100(self):
        outcome = combine([("nice", 1, MET)])
        assert (outcome.score, outcome.must_score) == (D("100.0"), None)

    def test_no_requirements_has_no_score(self):
        assert combine([]) is None


class TestGrades:
    @pytest.mark.parametrize(
        "score,grade",
        [(100, "A"), (85, "A"), ("84.9", "B"), (70, "B"), ("69.9", "C"), (55, "C"),
         ("54.9", "D"), (40, "D"), ("39.9", "E"), (0, "E")],
    )  # fmt: skip
    def test_the_grade_limits(self, score, grade):
        # must met, nice missing: the split itself is the score
        outcome = combine(
            [("must", 1, MET), ("nice", 1, MISSING)], (D(str(score)), 100 - D(str(score)))
        )
        assert (outcome.score, outcome.grade) == (D(str(score)).quantize(D("0.1")), grade)

    def test_a_score_rounds_half_up_to_one_decimal_and_the_grade_follows_it(self):
        outcome = combine([("must", 1, MET), ("nice", 1, MISSING)], (D("84.95"), D("15.05")))
        assert (outcome.score, outcome.grade) == (D("85.0"), "A")

    def test_the_limits_are_platform_settings(self):
        set_setting("scoring.grade_a_min", 90)
        assert combine([("must", 1, MET), ("nice", 1, MISSING)], (D(88), D(12))).grade == "B"

    def test_the_points_are_platform_settings(self):
        set_setting("scoring.points_partly_met", 40)
        assert combine([("must", 1, PARTLY)]).score == D("40.0")


class TestTheCap:
    ENTRIES = [("must", 1, MISSING), ("must", 3, MET), ("nice", 1, MET)]  # 75*.7+100*.3 = 82.5

    def test_off_by_default_nothing_is_capped(self):
        outcome = combine(self.ENTRIES)
        assert (outcome.score, outcome.capped) == (D("82.5"), False)

    def test_on_a_missing_must_have_caps_at_60(self):
        outcome = combine(self.ENTRIES, cap=True)
        assert (outcome.score, outcome.grade, outcome.capped) == (D("60.0"), "C", True)

    def test_a_score_already_below_the_cap_is_not_touched(self):
        outcome = combine([("must", 1, MISSING), ("must", 1, MISSING), ("nice", 1, MET)], cap=True)
        assert (outcome.score, outcome.capped) == (D("30.0"), False)

    def test_a_partly_met_must_have_is_not_missing(self):
        assert combine([("must", 1, PARTLY), ("nice", 1, MET)], cap=True).capped is False

    def test_a_missing_nice_to_have_never_caps(self):
        assert combine([("must", 1, MET), ("nice", 1, MISSING)], cap=True).capped is False

    def test_the_cap_value_is_a_platform_setting(self):
        set_setting("scoring.missing_must_have_cap", 50)
        assert combine(self.ENTRIES, cap=True).score == D("50.0")


def make_scored(verdicts=((("must", 3), MET), (("must", 1), MISSING), (("nice", 1), PARTLY))):
    """A candidate with one stored result for each (kind, weight), verdict."""
    cv = add_profile(make_cv())
    candidate = candidates.create_candidate(cv)
    for position, ((kind, weight), verdict) in enumerate(verdicts, 1):
        requirement = Requirement.objects.create(
            company_id=cv.company_id,
            project=cv.project,
            position=position,
            kind=kind,
            text=f"Requirement {position}",
            weight=weight,
        )
        RequirementResult.objects.create(
            company_id=cv.company_id,
            candidate=candidate,
            requirement=requirement,
            requirement_text=requirement.text,
            verdict=verdict,
            evidence="" if verdict == MISSING else "a quote",
            confidence="high",
            model="m",
            prompt_version=1,
        )
    return candidate


class TestStoredScore:
    def test_the_score_is_stored_with_its_grade_and_group_scores(self):
        stored = scoring.score_candidate(make_scored())
        assert (stored.score, stored.grade) == (D("67.5"), "C")
        assert (stored.must_score, stored.nice_score, stored.capped) == (
            D("75.0"),
            D("50.0"),
            False,
        )

    def test_scoring_again_keeps_one_row(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        scoring.score_candidate(candidate)
        assert CandidateScore.objects.filter(candidate=candidate).count() == 1

    def test_the_project_cap_switch_is_used(self):
        candidate = make_scored()
        ProjectScoringSettings.objects.create(
            company_id=candidate.company_id,
            project=candidate.project,
            must_weight_percent=30,
            nice_weight_percent=70,
            recommendation_threshold=75,
            top_n=10,
            cap_on_missing_must_have=True,
        )
        # must 75, nice 50 -> 75*.3 + 50*.7 = 57.5, already below the cap
        assert scoring.score_candidate(candidate).score == D("57.5")
        set_setting("scoring.missing_must_have_cap", 55)
        assert scoring.score_candidate(candidate).capped is True

    def test_the_default_for_a_project_without_settings_is_the_platform_setting(self):
        candidate = make_scored()
        set_setting("scoring.cap_on_missing_must_have", True)
        set_setting("scoring.missing_must_have_cap", 40)
        assert scoring.score_candidate(candidate).score == D("40.0")

    def test_only_the_requirements_count(self):
        candidate = make_scored()
        from cvs.models import AtsScore

        AtsScore.objects.create(
            company_id=candidate.company_id, candidate=candidate, score=0,
            job_description_hash="x", rules_version=1,
        )  # fmt: skip
        assert scoring.score_candidate(candidate).score == D("67.5")

    def test_a_requirement_not_judged_yet_leaves_the_score_alone(self):
        candidate = make_scored()
        before = scoring.score_candidate(candidate)
        Requirement.objects.create(
            company_id=candidate.company_id, project=candidate.project, position=9,
            kind="nice", text="New one", weight=1,
        )  # fmt: skip
        assert scoring.score_candidate(candidate) is None
        assert CandidateScore.objects.get(candidate=candidate).score == before.score

    def test_a_requirement_edited_since_it_was_judged_leaves_the_score_alone(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        Requirement.objects.filter(project=candidate.project).update(text="Edited wording")
        assert scoring.score_candidate(candidate) is None

    def test_a_project_without_requirements_has_nothing_to_score(self):
        cv = add_profile(make_cv())
        assert scoring.score_candidate(candidates.create_candidate(cv)) is None


class TestChangingWeights:
    def test_a_requirement_weight_recalculates_at_once_with_no_ai(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        project = candidate.project
        items = [
            {
                **{key: r[key] for key in ("id", "kind", "text")},
                "weight": 1 if r["weight"] == 3 else r["weight"],
            }
            for r in list_requirements(project)
        ]
        save_requirements(project.pk, project.company_id, items, acknowledge_rescoring=True)
        # must: (1*100 + 1*0)/2 = 50; 50*.7 + 50*.3 = 50
        assert CandidateScore.objects.get(candidate=candidate).score == D("50.0")

    def test_the_split_recalculates_at_once_with_no_ai(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        project = candidate.project
        saved = scoring_settings.save_scoring_settings(
            project.pk, project.company_id,
            {"must_weight_percent": 50, "nice_weight_percent": 50, "recommendation_threshold": 75,
             "top_n": 10, "cap_on_missing_must_have": False},
        )  # fmt: skip
        assert saved["recalculated"] == 1
        assert CandidateScore.objects.get(candidate=candidate).score == D("62.5")

    def test_switching_the_cap_on_recalculates(self):
        candidate = make_scored([(("must", 1), MISSING), (("must", 3), MET), (("nice", 1), MET)])
        scoring.score_candidate(candidate)
        project = candidate.project
        scoring_settings.save_scoring_settings(
            project.pk, project.company_id,
            {"must_weight_percent": 70, "nice_weight_percent": 30, "recommendation_threshold": 75,
             "top_n": 10, "cap_on_missing_must_have": True},
        )  # fmt: skip
        stored = CandidateScore.objects.get(candidate=candidate)
        assert (stored.score, stored.capped) == (D("60.0"), True)

    def test_an_unchanged_save_recalculates_nothing(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        assert scoring.recalculate_project(candidate.project) == 0

    def test_a_new_score_counts_as_changed(self):
        candidate = make_scored()
        assert scoring.recalculate_project(candidate.project) == 1


class TestTheStep:
    def test_the_step_is_plugged_into_the_scoring_slot(self):
        assert processing.STEPS["scoring"].__name__ == "calculate_the_score"

    def test_the_step_stores_the_score_of_the_candidate(self):
        candidate = make_scored()

        class Context:
            cv_file = candidate.cv_file
            state = {}

        scoring.calculate_the_score(Context)
        assert CandidateScore.objects.get(candidate=candidate).grade == "C"

    def test_an_unjudged_candidate_fails_with_a_plain_reason(self):
        cv = add_profile(make_cv())
        candidate = candidates.create_candidate(cv)

        class Context:
            cv_file = candidate.cv_file
            state = {}

        with pytest.raises(PermanentFailure) as failure:
            scoring.calculate_the_score(Context)
        assert "retry" in str(failure.value)
