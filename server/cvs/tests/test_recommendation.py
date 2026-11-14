from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from core.tests.factories import start_session_for
from cvs import recommendation, scoring
from cvs.models import CandidateScore
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_score_calculation import MET, MISSING, PARTLY, make_scored
from projects import scoring_settings
from projects.models import Requirement

pytestmark = pytest.mark.django_db

D = Decimal
THRESHOLD = 75  # the platform default for Strong match; Possible starts at 55


class TestTheLabel:
    @pytest.mark.parametrize(
        "score,label",
        [
            (100, "strong_match"),
            (75, "strong_match"),
            ("74.9", "possible"),
            (55, "possible"),
            ("54.9", "not_recommended"),
            (0, "not_recommended"),
        ],
    )
    def test_the_label_rules(self, score, label):
        assert recommendation.label_for(D(str(score)), THRESHOLD) == label

    def test_the_project_threshold_decides_strong_match(self):
        assert recommendation.label_for(D(80), 85) == "possible"
        assert recommendation.label_for(D(60), 60) == "strong_match"

    def test_the_possible_limit_is_a_platform_setting(self):
        set_setting("scoring.possible_match_min", 65)
        assert recommendation.label_for(D(60), THRESHOLD) == "not_recommended"

    def test_a_threshold_below_the_possible_limit_leaves_no_possible_band(self):
        assert recommendation.label_for(D(50), 50) == "strong_match"
        assert recommendation.label_for(D("49.9"), 50) == "not_recommended"


class TestBorderline:
    @pytest.mark.parametrize(
        "score,borderline",
        [(75, True), (72, True), ("71.9", False), (78, True), ("78.1", False), (55, True),
         (52, True), ("51.9", False), (58, True), ("58.1", False), (65, False), (100, False),
         (0, False)],
    )  # fmt: skip
    def test_within_three_points_of_either_limit(self, score, borderline):
        assert recommendation.is_borderline(D(str(score)), THRESHOLD) is borderline

    def test_the_distance_is_a_platform_setting(self):
        set_setting("recommendation.borderline_points", 5)
        assert recommendation.is_borderline(D(70), THRESHOLD) is True

    def test_it_follows_the_project_threshold(self):
        assert recommendation.is_borderline(D(88), 90) is True
        assert recommendation.is_borderline(D(88), 75) is False


def judged_of(*items):
    """(requirement, verdict) pairs for (kind, weight, verdict, text) items."""
    return [
        (Requirement(kind=kind, weight=weight, text=text, position=position), verdict)
        for position, (kind, weight, verdict, text) in enumerate(items, 1)
    ]


class TestInsights:
    JUDGED = judged_of(
        ("must", 1, MET, "M-light"),
        ("must", 5, MET, "M-heavy"),
        ("nice", 9, MET, "N-heaviest"),
        ("nice", 2, MET, "N-light"),
        ("must", 2, PARTLY, "P-must"),
        ("nice", 4, MISSING, "X-nice"),
        ("must", 3, MISSING, "X-must"),
    )

    def texts(self, items):
        return [item["requirement"] for item in items]

    def test_strengths_are_the_met_ones_must_haves_and_heavier_first_up_to_three(self):
        assert self.texts(recommendation.strengths(self.JUDGED)) == [
            "M-heavy", "M-light", "N-heaviest",
        ]  # fmt: skip

    def test_risks_are_the_missing_and_partly_met_ones_up_to_three(self):
        assert self.texts(recommendation.risks(self.JUDGED)) == ["X-must", "P-must", "X-nice"]

    def test_a_risk_says_what_is_wrong(self):
        risk = recommendation.risks(self.JUDGED)[0]
        assert risk == {"requirement": "X-must", "kind": "must", "verdict": "missing"}

    def test_the_questions_probe_the_gaps_first_up_to_five(self):
        questions = recommendation.interview_questions(self.JUDGED)
        assert len(questions) == 5
        assert "X-must" in questions[0] and "does not show" in questions[0]
        assert "P-must" in questions[1] and "part of this" in questions[1]
        assert "X-nice" in questions[2]
        assert "M-heavy" in questions[3] and "example" in questions[3]
        assert "M-light" in questions[4]

    def test_no_gaps_means_no_risks_and_questions_check_what_is_met(self):
        judged = judged_of(("must", 1, MET, "Only one"))
        assert recommendation.risks(judged) == []
        assert recommendation.interview_questions(judged) == [
            "Can you give an example from your recent work of: Only one?"
        ]

    def test_nothing_met_means_no_strengths(self):
        assert recommendation.strengths(judged_of(("must", 1, MISSING, "x"))) == []

    def test_the_limits_are_platform_settings(self):
        set_setting("recommendation.max_strengths", 1)
        set_setting("recommendation.max_risks", 2)
        set_setting("recommendation.max_questions", 2)
        assert len(recommendation.strengths(self.JUDGED)) == 1
        assert len(recommendation.risks(self.JUDGED)) == 2
        assert len(recommendation.interview_questions(self.JUDGED)) == 2

    def test_a_question_template_is_a_platform_setting(self):
        set_setting("recommendation.question_missing", "Tell us about {requirement}.")
        judged = judged_of(("must", 1, MISSING, "Python"))
        assert recommendation.interview_questions(judged) == ["Tell us about Python."]

    def test_the_same_inputs_give_the_same_insights(self):
        again = recommendation.recommend(D(60), THRESHOLD, list(reversed(self.JUDGED)))
        assert again == recommendation.recommend(D(60), THRESHOLD, self.JUDGED)


class TestStoredWithTheScore:
    def test_the_recommendation_is_stored_with_the_score(self):
        stored = scoring.score_candidate(make_scored())  # 67.5
        assert (stored.label, stored.borderline) == ("possible", False)
        assert [r["requirement"] for r in stored.strengths] == ["Requirement 1"]
        assert [r["requirement"] for r in stored.risks] == ["Requirement 2", "Requirement 3"]
        assert len(stored.interview_questions) == 3
        assert stored.guide_note == "This is a guide. The recruiter decides."

    def test_the_guide_note_is_a_platform_setting(self):
        set_setting("recommendation.guide_note", "A guide only.")
        assert scoring.score_candidate(make_scored()).guide_note == "A guide only."

    def test_the_stored_label_is_always_a_known_one(self):
        from django.db import IntegrityError, transaction

        stored = scoring.score_candidate(make_scored())
        with pytest.raises(IntegrityError), transaction.atomic():
            CandidateScore.objects.filter(pk=stored.pk).update(label="great")

    def test_a_threshold_change_recalculates_the_label_with_no_ai(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        project = candidate.project
        saved = scoring_settings.save_scoring_settings(
            project.pk, project.company_id,
            {"must_weight_percent": 70, "nice_weight_percent": 30, "recommendation_threshold": 65,
             "top_n": 10, "cap_on_missing_must_have": False},
        )  # fmt: skip
        stored = CandidateScore.objects.get(candidate=candidate)
        assert (saved["recalculated"], stored.label, stored.borderline) == (1, "strong_match", True)

    def test_the_recommendation_does_not_hold_cv_text(self):
        stored = scoring.score_candidate(make_scored())
        assert "a quote" not in str([stored.strengths, stored.risks, stored.interview_questions])


class TestTheApi:
    def url(self, candidate, project=None):
        project = project or candidate.project
        return f"/api/company/projects/{project.pk}/candidates/{candidate.pk}/recommendation/"

    def client_for(self, candidate):
        issued = start_session_for(
            user_id=candidate.project.created_by_id,
            role="owner",
            company_id=candidate.company_id,
            kind="company",
        )
        return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")

    def test_it_shows_the_score_and_the_insights(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        body = self.client_for(candidate).get(self.url(candidate)).json()
        assert (body["score"], body["grade"], body["label"], body["borderline"]) == (
            "67.5", "C", "possible", False,
        )  # fmt: skip
        assert body["guide_note"] == "This is a guide. The recruiter decides."
        assert body["strengths"][0]["requirement"] == "Requirement 1"
        assert len(body["interview_questions"]) == 3

    def test_a_candidate_not_scored_yet_is_not_found(self):
        candidate = make_scored()
        assert self.client_for(candidate).get(self.url(candidate)).status_code == 404

    def test_another_companys_candidate_is_not_found(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        stranger = make_scored()
        assert self.client_for(stranger).get(self.url(candidate)).status_code == 404

    def test_a_candidate_of_another_project_is_not_found_under_this_one(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        other = make_scored()
        client = self.client_for(candidate)
        assert client.get(self.url(candidate, project=other.project)).status_code == 404

    def test_signed_out_is_refused(self):
        candidate = make_scored()
        scoring.score_candidate(candidate)
        assert APIClient().get(self.url(candidate)).status_code == 401
