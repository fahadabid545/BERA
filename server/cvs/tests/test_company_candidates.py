import pytest

from cvs.models import Candidate
from cvs.tests.test_candidate_filters import judge, requirement
from cvs.tests.test_dashboard import move, second_project
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add

pytestmark = pytest.mark.django_db
URL = "/api/company/candidates/"


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def page(tenant, query=""):
    response = tenant.client.get(f"{URL}{query}")
    assert response.status_code == 200, response.content
    return response.json()


def names(tenant, query=""):
    return [row["file_name"] for row in page(tenant, query)["rows"]]


@pytest.fixture
def pool(tenant):
    other = second_project(tenant, "Second project")
    first = add(tenant, "anna.pdf", 90, ats=80, minutes=1)
    second = add(tenant, "ben.pdf", 72, ats=60, minutes=2)
    third = add(other, "cara.pdf", 55, ats=95, minutes=3)
    add(tenant, "waiting.pdf", None, minutes=4)  # no candidate yet: never listed
    move(tenant, first, "shortlisted")
    move(tenant, third, "rejected")
    return tenant, other, (first, second, third)


class TestTheList:
    def test_every_project_in_one_list_best_score_first(self, pool):
        tenant, other, _ = pool
        body = page(tenant)
        assert [row["file_name"] for row in body["rows"]] == ["anna.pdf", "ben.pdf", "cara.pdf"]
        assert body["rows"][2]["project_title"] == "Second project"
        assert body["rows"][0]["ats_score"] == 80 and body["rows"][0]["score"] == "90.0"

    def test_rows_hold_what_the_page_links_to(self, pool):
        tenant, _, (first, _, _) = pool
        row = page(tenant)["rows"][0]
        assert row["id"] == str(first.candidate.pk)
        assert row["project_id"] == str(tenant.project.pk)
        assert row["stage"] == "shortlisted"

    def test_another_company_is_never_listed(self, pool):
        tenant, _, _ = pool
        stranger = Tenant(make_plan())
        add(stranger, "secret.pdf", 99)
        assert "secret.pdf" not in names(tenant)
        assert names(stranger) == ["secret.pdf"]

    def test_sorting_and_paging(self, pool):
        tenant, _, _ = pool
        set_setting("candidates.page_size", 2)
        body = page(tenant, "?sort=ats&direction=asc")
        assert [row["file_name"] for row in body["rows"]] == ["ben.pdf", "anna.pdf"]
        assert (body["page"], body["pages"], body["count"]) == (1, 2, 3)
        assert names(tenant, "?sort=ats&direction=asc&page=2") == ["cara.pdf"]
        assert page(tenant, "?page=99")["page"] == 2

    def test_a_bad_sort_or_page_is_refused(self, pool):
        tenant, _, _ = pool
        for query in ("?sort=x", "?page=0", "?direction=up"):
            assert tenant.client.get(f"{URL}{query}").status_code == 400


class TestTheFlags:
    def test_the_tabs_count_each_flag_and_all(self, pool):
        tenant, _, _ = pool
        flags = page(tenant)["flags"]
        assert flags["all"] == 3
        assert (flags["new"], flags["shortlisted"], flags["rejected"]) == (1, 1, 1)
        assert flags["interviewed"] == flags["on_hold"] == flags["selected"] == 0

    def test_a_flag_shows_only_its_candidates_and_all_includes_rejected(self, pool):
        tenant, _, _ = pool
        assert names(tenant, "?flag=shortlisted") == ["anna.pdf"]
        assert names(tenant, "?flag=rejected") == ["cara.pdf"]
        assert "cara.pdf" in names(tenant, "?flag=all")
        assert names(tenant, "?flag=selected") == []

    def test_the_tab_counts_follow_the_filters_but_not_the_flag(self, pool):
        tenant, other, _ = pool
        body = page(tenant, f"?flag=new&project={other.project.pk}")
        assert body["flags"]["all"] == 1 and body["flags"]["rejected"] == 1
        assert body["rows"] == []

    def test_an_unknown_flag_is_refused(self, pool):
        tenant, _, _ = pool
        assert tenant.client.get(f"{URL}?flag=maybe").status_code == 400

    def test_a_changed_flag_moves_the_candidate(self, pool):
        tenant, _, (_, second, _) = pool
        move(tenant, second, "interviewed")
        assert names(tenant, "?flag=interviewed") == ["ben.pdf"]
        assert page(tenant)["flags"]["new"] == 0
        assert Candidate.objects.get(pk=second.candidate.pk).stage == "interviewed"


class TestTheFilters:
    def test_by_project(self, pool):
        tenant, other, _ = pool
        assert names(tenant, f"?project={other.project.pk}") == ["cara.pdf"]
        assert names(tenant, f"?project={tenant.project.pk}") == ["anna.pdf", "ben.pdf"]

    def test_another_companys_project_or_a_bad_id_is_not_found(self, pool):
        tenant, _, _ = pool
        stranger = Tenant(make_plan())
        assert tenant.client.get(f"{URL}?project={stranger.project.pk}").status_code == 404
        assert tenant.client.get(f"{URL}?project=nope").status_code == 404

    def test_by_ai_score_and_ats_score(self, pool):
        tenant, _, _ = pool
        assert names(tenant, "?score_min=60") == ["anna.pdf", "ben.pdf"]
        assert names(tenant, "?score_max=60") == ["cara.pdf"]
        assert names(tenant, "?ats_min=70&ats_max=90") == ["anna.pdf"]
        assert tenant.client.get(f"{URL}?score_min=x").status_code == 400
        assert tenant.client.get(f"{URL}?ats_min=9&ats_max=1").status_code == 400

    def test_by_grade_label_and_search(self, pool):
        tenant, _, _ = pool
        assert names(tenant, "?grade=A") == ["anna.pdf"]
        assert names(tenant, "?q=BEN") == ["ben.pdf"]
        assert tenant.client.get(f"{URL}?label=bad").status_code == 400

    def test_by_what_is_missing(self, pool):
        tenant, _, (first, second, third) = pool
        must = requirement(tenant, "Python", "must")
        nice = requirement(tenant, "Docker", "nice", position=2)
        judge(tenant, first, must, "missing")
        judge(tenant, second, nice, "missing")
        judge(tenant, third, must, "met")
        assert names(tenant, "?missing=must") == ["anna.pdf"]
        assert names(tenant, "?missing=nice") == ["ben.pdf"]
        assert names(tenant, "?missing=none") == ["cara.pdf"]
        row = page(tenant, "?missing=must")["rows"][0]
        assert (row["missing_must"], row["missing_nice"]) == (1, 0)
        assert tenant.client.get(f"{URL}?missing=lots").status_code == 400

    def test_filters_combine(self, pool):
        tenant, other, _ = pool
        assert names(tenant, f"?flag=shortlisted&project={tenant.project.pk}&score_min=80") == [
            "anna.pdf"
        ]
        assert names(tenant, f"?flag=shortlisted&project={other.project.pk}") == []

    def test_the_projects_to_filter_by_are_listed(self, pool):
        tenant, _, _ = pool
        assert {item["title"] for item in page(tenant)["projects"]} == {"T", "Second project"}


class TestWhoMayRead:
    def test_a_visitor_is_refused(self, pool):
        from rest_framework.test import APIClient

        assert APIClient().get(URL).status_code == 401

    def test_it_is_read_only(self, pool):
        tenant, _, _ = pool
        assert tenant.client.post(URL, {}, format="json").status_code == 405
