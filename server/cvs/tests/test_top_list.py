import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cvs.models import Candidate
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add, url
from cvs.top_list import top_list
from projects.models import ProjectScoringSettings

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def top_n(tenant, value):
    ProjectScoringSettings.objects.update_or_create(
        project=tenant.project,
        defaults={
            "company_id": tenant.company.pk, "must_weight_percent": 70, "nice_weight_percent": 30,
            "recommendation_threshold": 75, "top_n": value, "cap_on_missing_must_have": True,
        },
    )  # fmt: skip


def body(tenant, query=""):
    return tenant.client.get(url(tenant, query)).json()


def marked(tenant, query=""):
    return sorted(row["file_name"] for row in body(tenant, query)["rows"] if row["top"])


def fill(tenant, scores):
    for number, score in enumerate(scores):
        add(tenant, f"cv{number}.pdf", score, minutes=number)


class TestTopList:
    def test_the_default_is_ten_from_the_platform_setting(self, tenant):
        fill(tenant, range(12))
        assert top_list(tenant.project)["n"] == 10
        assert len(marked(tenant)) == 10
        assert body(tenant)["top"] == {"n": 10, "included": 10, "tied": False}

    def test_the_best_n_by_score_are_marked(self, tenant):
        top_n(tenant, 2)
        add(tenant, "low.pdf", 40)
        add(tenant, "best.pdf", 95, minutes=1)
        add(tenant, "good.pdf", 80, minutes=2)
        assert marked(tenant) == ["best.pdf", "good.pdf"]

    def test_ties_at_the_cut_off_are_all_marked_with_a_note_flag(self, tenant):
        top_n(tenant, 2)
        add(tenant, "best.pdf", 95)
        add(tenant, "tie1.pdf", 80, minutes=1)
        add(tenant, "tie2.pdf", 80, minutes=2)
        add(tenant, "tie3.pdf", 80, minutes=3)
        add(tenant, "low.pdf", 50, minutes=4)
        assert marked(tenant) == ["best.pdf", "tie1.pdf", "tie2.pdf", "tie3.pdf"]
        assert body(tenant)["top"] == {"n": 2, "included": 4, "tied": True}

    def test_a_tie_inside_the_list_is_not_a_tie_at_the_cut_off(self, tenant):
        top_n(tenant, 3)
        add(tenant, "a.pdf", 90)
        add(tenant, "b.pdf", 90, minutes=1)
        add(tenant, "c.pdf", 70, minutes=2)
        add(tenant, "d.pdf", 50, minutes=3)
        assert marked(tenant) == ["a.pdf", "b.pdf", "c.pdf"]
        assert body(tenant)["top"]["tied"] is False

    def test_n_larger_than_the_candidates_marks_every_scored_one(self, tenant):
        top_n(tenant, 10)
        fill(tenant, [60, 70])
        add(tenant, "waiting.pdf", status="waiting", minutes=9)
        assert marked(tenant) == ["cv0.pdf", "cv1.pdf"]
        assert body(tenant)["top"] == {"n": 10, "included": 2, "tied": False}
        assert not [r for r in body(tenant)["rows"] if r["file_name"] == "waiting.pdf"][0]["top"]

    def test_no_candidates_at_all(self, tenant):
        assert body(tenant)["top"] == {"n": 10, "included": 0, "tied": False}

    def test_n_of_one_with_a_tie_for_first(self, tenant):
        top_n(tenant, 1)
        fill(tenant, [90, 90, 10])
        assert marked(tenant) == ["cv0.pdf", "cv1.pdf"]
        assert body(tenant)["top"]["tied"] is True

    def test_the_plan_caps_n(self):
        tenant = Tenant(make_plan(max_top_n=2))
        top_n(tenant, 10)
        fill(tenant, [10, 20, 30, 40])
        assert top_list(tenant.project)["n"] == 2
        assert marked(tenant) == ["cv2.pdf", "cv3.pdf"]

    def test_rejected_candidates_are_not_in_the_top_and_the_next_one_moves_up(self, tenant):
        top_n(tenant, 2)
        fill(tenant, [90, 80, 70])
        Candidate.objects.filter(cv_file__original_name="cv0.pdf").update(stage="rejected")
        assert marked(tenant) == ["cv1.pdf", "cv2.pdf"]
        shown = body(tenant, "?stage=rejected")["rows"]
        assert shown[0]["top"] is False

    def test_it_is_live_a_new_better_candidate_pushes_one_out(self, tenant):
        top_n(tenant, 2)
        fill(tenant, [90, 80])
        assert marked(tenant) == ["cv0.pdf", "cv1.pdf"]
        add(tenant, "new.pdf", 85, minutes=20)
        assert marked(tenant) == ["cv0.pdf", "new.pdf"]

    def test_the_top_does_not_depend_on_the_filters(self, tenant):
        top_n(tenant, 1)
        fill(tenant, [90, 50])
        assert marked(tenant, "?score_max=60") == []
        assert body(tenant, "?score_max=60")["top"]["included"] == 1

    def test_it_stays_inside_the_project_and_company(self, tenant):
        top_n(tenant, 1)
        other = Tenant(make_plan())
        add(other, "theirs.pdf", 99)
        fill(tenant, [10])
        assert marked(tenant) == ["cv0.pdf"]

    def test_the_query_count_does_not_grow_with_candidates(self, tenant):
        fill(tenant, [10, 20])
        with CaptureQueriesContext(connection) as small:
            body(tenant)
        for number in range(10):
            add(tenant, f"more{number}.pdf", 30 + number, minutes=40 + number)
        with CaptureQueriesContext(connection) as large:
            body(tenant)
        assert len(large) == len(small)

    def test_the_setting_default_can_be_changed_by_the_platform(self, tenant):
        set_setting("scoring.top_n", 1)
        fill(tenant, [90, 10])
        assert marked(tenant) == ["cv0.pdf"]
