import pytest

from cvs import candidates
from cvs.board import latest_role
from cvs.models import Candidate, CvFile, CvProfile
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def board_of(tenant, query=""):
    response = tenant.client.get(
        f"/api/company/projects/{tenant.project.pk}/candidates/board/{query}"
    )
    assert response.status_code == 200, response.content
    return {column["stage"]: column for column in response.json()["columns"]}


def move(tenant, name, stage):
    row = CvFile.objects.get(original_name=name)
    Candidate.objects.filter(cv_file=row).update(stage=stage)


class TestColumns:
    def test_there_is_a_column_for_every_stage_in_order(self, tenant):
        response = tenant.client.get(f"/api/company/projects/{tenant.project.pk}/candidates/board/")
        assert [column["stage"] for column in response.json()["columns"]] == [
            "new", "shortlisted", "interviewed", "on_hold", "selected", "rejected",
        ]  # fmt: skip

    def test_a_project_with_no_candidates_has_empty_columns(self, tenant):
        assert all(
            column["count"] == 0 and column["cards"] == [] for column in board_of(tenant).values()
        )

    def test_cards_sit_in_their_stage_best_score_first(self, tenant):
        add(tenant, "low.pdf", 40)
        add(tenant, "high.pdf", 90)
        add(tenant, "short.pdf", 70)
        move(tenant, "short.pdf", "shortlisted")
        columns = board_of(tenant)
        assert [card["file_name"] for card in columns["new"]["cards"]] == ["high.pdf", "low.pdf"]
        assert [card["file_name"] for card in columns["shortlisted"]["cards"]] == ["short.pdf"]

    def test_rejected_candidates_have_their_own_column(self, tenant):
        add(tenant, "no.pdf", 30)
        move(tenant, "no.pdf", "rejected")
        columns = board_of(tenant)
        assert columns["rejected"]["count"] == 1 and columns["new"]["count"] == 0

    def test_a_cv_still_on_its_way_is_not_a_card(self, tenant):
        add(tenant, "waiting.pdf", status="waiting")
        add(tenant, "ready.pdf", 80)
        columns = board_of(tenant)
        assert columns["new"]["count"] == 1

    def test_a_column_loads_a_limited_number_but_counts_them_all(self, tenant):
        set_setting("candidates.board_column_size", 2)
        for index in range(3):
            add(tenant, f"c{index}.pdf", 50 + index)
        new = board_of(tenant)["new"]
        assert new["count"] == 3
        assert [card["file_name"] for card in new["cards"]] == ["c2.pdf", "c1.pdf"]

    def test_the_lists_filters_apply(self, tenant):
        add(tenant, "high.pdf", 90)
        add(tenant, "low.pdf", 40)
        assert [
            card["file_name"] for card in board_of(tenant, "?score_min=80")["new"]["cards"]
        ] == ["high.pdf"]

    def test_a_wrong_filter_is_refused_with_the_field(self, tenant):
        response = tenant.client.get(
            f"/api/company/projects/{tenant.project.pk}/candidates/board/?score_min=abc"
        )
        assert response.status_code == 400
        assert "score_min" in response.json()["error"]["fields"]


class TestCards:
    def test_a_card_has_key_name_role_and_score(self, tenant):
        row = add(tenant, "a.pdf", 82.5)
        CvProfile.objects.filter(cv_file=row).update(
            content={"jobs": [{"title": "Sales Manager", "start": "2020", "end": "present"}]}
        )
        card = board_of(tenant)["new"]["cards"][0]
        assert card["key"] == "BE-1" and card["role"] == "Sales Manager"
        assert (card["score"], card["grade"], card["name"]) == ("82.5", "B", "J. E.")

    def test_the_key_prefix_is_a_setting(self, tenant):
        add(tenant, "a.pdf", 80)
        set_setting("candidates.key_prefix", "HR")
        assert board_of(tenant)["new"]["cards"][0]["key"] == "HR-1"

    def test_the_full_name_never_leaves_the_server(self, tenant):
        add(tenant, "a.pdf", 80)
        response = tenant.client.get(f"/api/company/projects/{tenant.project.pk}/candidates/board/")
        assert "Jane" not in response.content.decode() and "jane@" not in response.content.decode()


class TestLatestRole:
    @pytest.mark.parametrize(
        "content, role",
        [
            ({}, ""),
            ({"jobs": []}, ""),
            ({"jobs": [{"title": "Old", "start": "2010", "end": "2012"},
                       {"title": "Newer", "start": "2013", "end": "2018-06"}]}, "Newer"),
            ({"jobs": [{"title": "Done", "start": "2015", "end": "2020"},
                       {"title": "Current", "start": "2019", "end": "present"}]}, "Current"),
            ({"jobs": [{"title": "Undated", "start": None, "end": None},
                       {"title": "Dated", "start": "2001", "end": None}]}, "Dated"),
        ],
    )  # fmt: skip
    def test_the_current_or_most_recent_job(self, content, role):
        assert latest_role(content) == role

    def test_a_missing_profile_content_is_empty(self):
        assert latest_role(None) == ""


class TestIsolation:
    def test_another_companys_project_is_not_found(self, tenant):
        stranger = Tenant(make_plan())
        add(stranger, "secret-other.pdf", 99)
        response = tenant.client.get(
            f"/api/company/projects/{stranger.project.pk}/candidates/board/"
        )
        assert response.status_code == 404
        assert "secret-other" not in response.content.decode()


class TestNumbers:
    def test_candidates_are_numbered_in_order_within_their_project(self, tenant):
        for name in ("a.pdf", "b.pdf", "c.pdf"):
            add(tenant, name, 50)
        numbers = Candidate.objects.order_by("number").values_list(
            "cv_file__original_name", "number"
        )
        assert list(numbers) == [("a.pdf", 1), ("b.pdf", 2), ("c.pdf", 3)]

    def test_a_retry_finds_the_same_candidate_and_number(self, tenant):
        row = add(tenant, "a.pdf", 50)
        again = candidates.create_candidate(row)
        assert again.number == 1 and Candidate.objects.count() == 1

    def test_a_second_project_starts_again_at_one(self, tenant):
        from projects.models import Project

        add(tenant, "a.pdf", 50)
        other = Project.objects.create(
            company=tenant.company, title="Other", job_description="x",
            reading_model="m", created_by=tenant.project.created_by,
        )  # fmt: skip
        tenant.project = other
        add(tenant, "b.pdf", 50)
        assert sorted(Candidate.objects.values_list("number", flat=True)) == [1, 1]
