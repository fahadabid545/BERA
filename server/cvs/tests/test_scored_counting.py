"""A CV counts against the month's limit once, when it has been scored (BERA-124)."""

import pytest

from cvs import candidates, duplicates, evaluation, processing, scoring
from cvs.models import CvFile
from cvs.tests.test_ai_reading import StubAi
from cvs.tests.test_candidate_record import add_profile, make_cv
from cvs.tests.test_requirement_evaluation import (
    CV_TEXT,
    PYTHON,
    add_requirements,
    answer,
    entry,
)
from usage import service as usage
from usage.models import CvUsage

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai(monkeypatch):
    return StubAi(monkeypatch)


def judged(ai, cv):
    """A CV with a candidate whose single requirement has been judged, ready to be scored."""
    add_requirements(cv.project, "Python experience")
    candidate = candidates.create_candidate(cv)
    ai.answers = [answer(entry(1, "met", PYTHON))]
    evaluation.evaluate_candidate(candidate, CV_TEXT)
    return candidate


def run_scoring_step(cv):
    scoring.calculate_the_score(processing.StepContext(cv, cv.company_id, cv.project_id))


def scored_count(cv):
    return usage.current_usage(cv.company_id)["cvs_scored"]


class TestScoringCounts:
    def test_a_scored_cv_is_counted(self, ai):
        cv = add_profile(make_cv())
        judged(ai, cv)
        assert scored_count(cv) == 0
        run_scoring_step(cv)
        assert scored_count(cv) == 1
        assert usage.is_counted(cv.company_id, cv.pk)

    def test_scoring_again_does_not_count_it_twice(self, ai):
        cv = add_profile(make_cv())
        judged(ai, cv)
        run_scoring_step(cv)
        run_scoring_step(cv)
        assert scored_count(cv) == 1

    def test_a_cv_that_could_not_be_scored_is_not_counted(self, ai):
        cv = add_profile(make_cv())
        add_requirements(cv.project, "Python experience")
        candidates.create_candidate(cv)  # nothing judged yet
        with pytest.raises(scoring.ResultsOutOfDate):
            run_scoring_step(cv)
        assert scored_count(cv) == 0

    def test_a_flagged_duplicate_is_not_counted_until_it_is_kept(self, ai):
        cv = add_profile(make_cv())
        judged(ai, cv)
        CvFile.objects.filter(pk=cv.pk).update(review="flagged")
        cv.refresh_from_db()
        run_scoring_step(cv)
        assert scored_count(cv) == 0
        CvFile.objects.filter(pk=cv.pk).update(status="done")
        duplicates.keep_flagged_cv(CvFile.objects.get(pk=cv.pk))
        assert scored_count(cv) == 1

    def test_keeping_a_flagged_cv_that_is_not_scored_yet_counts_nothing(self, ai):
        cv = add_profile(make_cv())
        CvFile.objects.filter(pk=cv.pk).update(review="flagged", status="reading")
        duplicates.keep_flagged_cv(CvFile.objects.get(pk=cv.pk))
        assert scored_count(cv) == 0

    def test_a_cv_with_no_usage_record_fails_loudly_not_silently(self, ai):
        cv = add_profile(make_cv())
        judged(ai, cv)
        CvUsage.objects.filter(cv_id=cv.pk).delete()
        with pytest.raises(CvUsage.DoesNotExist):
            run_scoring_step(cv)
