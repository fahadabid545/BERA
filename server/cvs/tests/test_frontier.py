import pytest
from rest_framework.test import APIClient

from cvs.frontier import pareto
from cvs.models import Candidate, CandidateScore
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def frontier(tenant, query="", client=None):
    link = f"/api/company/projects/{tenant.project.pk}/frontier/{query}"
    return (client or tenant.client).get(link)


class TestPareto:
    def test_the_points_nobody_beats(self):
        points = [("a", 70, 96), ("b", 84, 94), ("c", 93, 91), ("d", 98, 84), ("e", 80, 84)]
        on, beaten = pareto(points)
        assert on == ["a", "b", "c", "d"]
        assert beaten == {"e": "b"} or beaten["e"] in {"b", "c", "d"}

    def test_a_single_point_and_nothing(self):
        assert pareto([("a", 1, 1)]) == (["a"], {})
        assert pareto([]) == ([], {})

    def test_equal_points_do_not_beat_each_other(self):
        on, beaten = pareto([("a", 5, 5), ("b", 5, 5)])
        assert set(on) == {"a", "b"} and beaten == {}

    def test_the_same_x_keeps_only_the_higher_y(self):
        on, beaten = pareto([("a", 5, 9), ("b", 5, 4)])
        assert on == ["a"] and beaten == {"b": "a"}

    def test_the_same_y_keeps_only_the_higher_x(self):
        on, beaten = pareto([("a", 9, 5), ("b", 4, 5)])
        assert on == ["a"] and beaten == {"b": "a"}

    def test_one_candidate_better_on_both_beats_everyone(self):
        on, beaten = pareto([("a", 9, 9), ("b", 4, 5), ("c", 1, 8)])
        assert on == ["a"] and set(beaten) == {"b", "c"}


class TestEndpoint:
    def make(self, tenant):
        # (AI score, ATS): a and c are not beaten; b is beaten by a; d has no ATS score.
        rows = {
            name: add(tenant, f"{name}.pdf", score, ats=ats, minutes=index)
            for index, (name, score, ats) in enumerate(
                [("a", 90, 80), ("b", 70, 60), ("c", 60, 95), ("d", 50, None)]
            )
        }
        return rows

    def test_marks_who_nobody_beats_and_who_beats_the_rest(self, tenant):
        rows = self.make(tenant)
        body = frontier(tenant).json()
        by_id = {point["id"]: point for point in body["points"]}
        a, b, c = (str(rows[name].candidate.pk) for name in "abc")
        assert set(body["frontier"]) == {a, c}
        assert body["frontier"] == [a, c]  # by the horizontal score, lowest first
        assert by_id[b]["beaten_by"] == a and by_id[a]["beaten_by"] is None
        assert (by_id[a]["x"], by_id[a]["y"]) == (80.0, 90.0)
        assert by_id[a]["name"] == "J. E." and by_id[a]["grade"] and by_id[a]["file_name"]
        assert body["total"] == 3 and body["left_out"] == 1 and body["axes"] == "ai_ats"
        assert body["choices"] == ["ai_ats", "must_nice"]

    def test_the_compare_limits_come_from_the_settings(self, tenant):
        assert frontier(tenant).json()["compare_limits"] == {"min": 2, "max": 4}
        set_setting("comparison.max_candidates", 3)
        assert frontier(tenant).json()["compare_limits"]["max"] == 3

    def test_the_must_have_and_nice_to_have_scores_can_be_chosen(self, tenant):
        rows = self.make(tenant)
        CandidateScore.objects.filter(candidate=rows["a"].candidate).update(
            must_score=90, nice_score=40
        )
        CandidateScore.objects.filter(candidate=rows["b"].candidate).update(
            must_score=80, nice_score=70
        )
        body = frontier(tenant, "?axes=must_nice").json()
        assert body["total"] == 2 and body["left_out"] == 2
        assert set(body["frontier"]) == {str(rows[n].candidate.pk) for n in "ab"}

    def test_other_pairs_are_refused_with_the_field(self, tenant):
        response = frontier(tenant, "?axes=nope")
        assert response.status_code == 400
        assert "axes" in response.json()["error"]["fields"]

    def test_rejected_candidates_are_not_placed(self, tenant):
        rows = self.make(tenant)
        Candidate.objects.filter(pk=rows["a"].candidate.pk).update(stage="rejected")
        body = frontier(tenant).json()
        assert str(rows["a"].candidate.pk) not in {p["id"] for p in body["points"]}
        assert body["total"] == 2

    def test_the_number_of_points_is_limited_but_the_frontier_is_kept(self, tenant):
        rows = self.make(tenant)
        set_setting("comparison.frontier_max_points", 10)
        for index in range(20):
            add(tenant, f"x{index}.pdf", 10 + index, ats=5, minutes=20 + index)
        body = frontier(tenant).json()
        assert body["total"] == 23 and len(body["points"]) == 10
        assert {str(rows["a"].candidate.pk), str(rows["c"].candidate.pk)} <= {
            p["id"] for p in body["points"]
        }

    def test_an_empty_project_gives_no_points(self, tenant):
        body = frontier(tenant).json()
        assert body["points"] == [] and body["frontier"] == [] and body["total"] == 0

    def test_only_the_projects_own_candidates_and_company(self, tenant):
        self.make(tenant)
        other = Tenant(make_plan())
        add(other, "theirs.pdf", 99, ats=99)
        assert frontier(tenant).json()["total"] == 3
        foreign = f"/api/company/projects/{other.project.pk}/frontier/"
        assert tenant.client.get(foreign).status_code == 404
        assert APIClient().get(foreign).status_code == 401
