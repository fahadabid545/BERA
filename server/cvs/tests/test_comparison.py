import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cvs.models import Candidate, CvFile, RequirementResult
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add
from projects.models import Requirement

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def requirement(tenant, text, kind="must", position=1):
    return Requirement.objects.create(
        company=tenant.company, project=tenant.project, position=position, kind=kind,
        text=text, weight=5,
    )  # fmt: skip


def judge(tenant, row, item, verdict):
    return RequirementResult.objects.create(
        company=tenant.company, candidate=row.candidate, requirement=item,
        requirement_text=item.text, verdict=verdict,
        evidence="" if verdict == "missing" else f"quote for {row.original_name}",
        confidence="high", model="m", prompt_version=1,
    )  # fmt: skip


def compare(tenant, rows, client=None):
    ids = ",".join(str(row.candidate.pk) for row in rows)
    link = f"/api/company/projects/{tenant.project.pk}/compare/?ids={ids}"
    return (client or tenant.client).get(link)


def matrix(tenant, query="", client=None):
    link = f"/api/company/projects/{tenant.project.pk}/matrix/{query}"
    return (client or tenant.client).get(link)


@pytest.fixture
def trio(tenant):
    rows = [add(tenant, f"{n}.pdf", score, ats=ats, minutes=i) for i, (n, score, ats) in enumerate(
        [("a", 90, 80), ("b", 70, None), ("c", 50, 40)]
    )]  # fmt: skip
    first, second = requirement(tenant, "Python"), requirement(tenant, "SQL", "nice", 2)
    judge(tenant, rows[0], first, "met")
    judge(tenant, rows[0], second, "partly_met")
    judge(tenant, rows[1], first, "missing")
    return rows


class TestSideBySide:
    def test_scores_and_each_requirement_next_to_each_other(self, tenant, trio):
        body = compare(tenant, trio[:2]).json()
        assert [item["text"] for item in body["requirements"]] == ["Python", "SQL"]
        first, second = body["candidates"]
        assert (first["file_name"], first["score"], first["grade"], first["ats_score"]) == (
            "a.pdf", "90.0", "A", 80,
        )  # fmt: skip
        assert second["ats_score"] is None and second["stage"] == "new"
        assert first["results"][0] == {
            "verdict": "met",
            "outdated": False,
            "evidence": "quote for a.pdf",
        }
        assert first["results"][1]["verdict"] == "partly_met"
        assert (
            second["results"][0]["verdict"] == "missing" and second["results"][0]["evidence"] == ""
        )

    def test_a_requirement_not_judged_yet_has_no_verdict(self, tenant, trio):
        second = compare(tenant, trio[:2]).json()["candidates"][1]
        assert second["results"][1] == {"verdict": None, "outdated": True, "evidence": ""}

    def test_a_requirement_edited_since_is_marked_outdated(self, tenant, trio):
        Requirement.objects.filter(text="Python").update(text="Python 3")
        assert compare(tenant, trio[:2]).json()["candidates"][0]["results"][0]["outdated"] is True

    def test_the_order_chosen_is_kept(self, tenant, trio):
        names = [
            c["file_name"]
            for c in compare(tenant, [trio[2], trio[0], trio[1]]).json()["candidates"]
        ]
        assert names == ["c.pdf", "a.pdf", "b.pdf"]

    def test_the_name_is_shown_as_initials(self, tenant, trio):
        assert compare(tenant, trio[:2]).json()["candidates"][0]["name"] == "J. E."

    def test_four_are_allowed_and_more_get_a_clear_message(self, tenant, trio):
        extra = [add(tenant, f"x{n}.pdf", 40, minutes=10 + n) for n in range(2)]
        assert compare(tenant, [*trio, extra[0]]).status_code == 200
        response = compare(tenant, [*trio, *extra])
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "too_many_to_compare"
        assert "up to 4" in error["message"]

    def test_the_limits_come_from_the_settings(self, tenant, trio):
        set_setting("comparison.max_candidates", 3)
        assert compare(tenant, trio).status_code == 200
        add(tenant, "d.pdf", 20, minutes=9)
        assert (
            compare(tenant, [*trio, CvFile.objects.get(original_name="d.pdf")]).status_code == 400
        )

    def test_fewer_than_two_are_refused_with_the_field(self, tenant, trio):
        response = compare(tenant, trio[:1])
        assert response.status_code == 400 and "ids" in response.json()["error"]["fields"]
        link = f"/api/company/projects/{tenant.project.pk}/compare/"
        assert tenant.client.get(link).status_code == 400

    def test_the_same_candidate_twice_counts_once(self, tenant, trio):
        assert compare(tenant, [trio[0], trio[0]]).status_code == 400

    def test_another_companys_candidate_or_a_wrong_id_is_not_found(self, tenant, trio):
        other = Tenant(make_plan())
        foreign = add(other, "theirs.pdf", 80)
        assert compare(tenant, [trio[0], foreign]).status_code == 404
        link = f"/api/company/projects/{tenant.project.pk}/compare/?ids={trio[0].candidate.pk},nope"
        assert tenant.client.get(link).status_code == 404

    def test_the_query_count_is_fixed(self, tenant, trio):
        with CaptureQueriesContext(connection) as three:
            compare(tenant, trio)
        for number in range(3):
            requirement(tenant, f"R{number}", position=5 + number)
        with CaptureQueriesContext(connection) as more:
            compare(tenant, trio)
        assert len(more) == len(three)


class TestMatrix:
    def test_every_candidate_against_every_requirement_best_first(self, tenant, trio):
        body = matrix(tenant).json()
        assert [item["text"] for item in body["requirements"]] == ["Python", "SQL"]
        assert [row["file_name"] for row in body["rows"]] == ["a.pdf", "b.pdf", "c.pdf"]
        assert [row["rank"] for row in body["rows"]] == [1, 2, 3]
        assert [cell["verdict"] for cell in body["rows"][0]["cells"]] == ["met", "partly_met"]
        assert [cell["verdict"] for cell in body["rows"][1]["cells"]] == ["missing", None]
        assert body["rows"][2]["cells"][0] == {"verdict": None, "outdated": True}

    def test_a_new_candidate_joins_on_its_own(self, tenant, trio):
        assert matrix(tenant).json()["count"] == 3
        add(tenant, "new.pdf", 99, minutes=30)
        body = matrix(tenant).json()
        assert body["count"] == 4 and body["rows"][0]["file_name"] == "new.pdf"
        assert len(body["rows"][0]["cells"]) == 2

    def test_a_new_requirement_adds_a_column(self, tenant, trio):
        requirement(tenant, "Docker", position=3)
        body = matrix(tenant).json()
        assert len(body["requirements"]) == 3 and all(len(r["cells"]) == 3 for r in body["rows"])

    def test_cvs_without_a_candidate_are_not_in_the_matrix(self, tenant, trio):
        add(tenant, "waiting.pdf", status="waiting", minutes=40)
        assert matrix(tenant).json()["count"] == 3

    def test_it_takes_the_filters_of_the_list(self, tenant, trio):
        body = matrix(tenant, "?score_min=60").json()
        assert [row["file_name"] for row in body["rows"]] == ["a.pdf", "b.pdf"] and body["filtered"]
        assert matrix(tenant, "?q=c.pdf").json()["count"] == 1
        assert matrix(tenant, "?score_min=abc").status_code == 400

    def test_rejected_are_left_out_unless_the_stage_filter_asks(self, tenant, trio):
        Candidate.objects.filter(pk=trio[0].candidate.pk).update(stage="rejected")
        assert matrix(tenant).json()["count"] == 2
        assert matrix(tenant, "?stage=rejected").json()["count"] == 1

    def test_it_is_paged(self, tenant, trio):
        set_setting("comparison.matrix_page_size", 2)
        first, second = matrix(tenant).json(), matrix(tenant, "?page=2").json()
        assert (first["pages"], len(first["rows"]), len(second["rows"])) == (2, 2, 1)
        assert matrix(tenant, "?page=9").json()["page"] == 2
        assert matrix(tenant, "?page=0").status_code == 400

    def test_only_the_projects_own_candidates(self, tenant, trio):
        other = Tenant(make_plan())
        add(other, "theirs.pdf", 99)
        assert "theirs.pdf" not in [r["file_name"] for r in matrix(tenant).json()["rows"]]

    def test_an_empty_project_gives_an_empty_matrix(self, tenant):
        body = matrix(tenant).json()
        assert body["rows"] == [] and body["pages"] == 1

    def test_the_query_count_does_not_grow_with_candidates(self, tenant, trio):
        with CaptureQueriesContext(connection) as small:
            matrix(tenant)
        for number in range(10):
            add(tenant, f"extra{number}.pdf", 40, minutes=50 + number)
        with CaptureQueriesContext(connection) as large:
            matrix(tenant)
        assert len(large) == len(small)


def test_the_candidate_list_tells_the_page_how_many_can_be_compared(tenant, trio):
    link = f"/api/company/projects/{tenant.project.pk}/candidates/"
    assert tenant.client.get(link).json()["compare_limits"] == {"min": 2, "max": 4}
