from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project

pytestmark = pytest.mark.django_db
URL = "/api/company/projects/"


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def make_project(company, person, title, *, status="active", age_days=0):
    project = Project.objects.create(
        company=company,
        title=title,
        job_description="text",
        reading_model="model",
        prompt_version="prompt",
        created_by=person,
        status=status,
    )
    Project.objects.filter(pk=project.pk).update(
        updated_at=timezone.now() - timedelta(days=age_days)
    )
    return project


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner(company):
    return sign_in(company)


def titles(response):
    return [row["title"] for row in response.json()["results"]]


class TestRows:
    def test_each_row_has_the_ticket_columns(self, company, owner):
        person, client = owner
        make_project(company, person, "Backend engineer")
        body = client.get(URL).json()
        row = body["results"][0]
        assert set(row) == {"id", "title", "cv_count", "best_score", "status", "updated_at"}
        assert row["title"] == "Backend engineer"
        assert row["status"] == "active"

    def test_cv_count_is_zero_and_best_score_empty_until_candidates_exist(self, company, owner):
        person, client = owner
        make_project(company, person, "A")
        row = client.get(URL).json()["results"][0]
        assert row["cv_count"] == 0
        assert row["best_score"] is None

    def test_an_empty_company_gets_an_empty_page(self, owner):
        _, client = owner
        body = client.get(URL).json()
        assert body["results"] == []
        assert (body["total"], body["pages"], body["page"]) == (0, 1, 1)

    def test_a_member_may_read_too(self, company):
        person, _ = sign_in(company)
        make_project(company, person, "A")
        _, member = sign_in(company, role="member")
        assert titles(member.get(URL)) == ["A"]

    def test_nobody_signed_in_is_refused(self):
        assert APIClient().get(URL).status_code == 401


class TestOnlyOwnProjects:
    def test_another_companys_projects_never_appear(self, company, owner):
        person, client = owner
        other = make_company()
        stranger, _ = sign_in(other)
        make_project(company, person, "Mine")
        make_project(other, stranger, "Theirs")
        body = client.get(URL, {"status": "all"}).json()
        assert titles(client.get(URL, {"status": "all"})) == ["Mine"]
        assert body["total"] == 1

    def test_search_and_paging_do_not_reach_other_companies_either(self, company, owner):
        person, client = owner
        other = make_company()
        stranger, _ = sign_in(other)
        make_project(other, stranger, "Secret engineer")
        assert titles(client.get(URL, {"search": "secret"})) == []
        make_project(company, person, "Open")
        assert client.get(URL, {"page": 2}).json()["results"] == []


class TestFilter:
    @pytest.fixture(autouse=True)
    def projects(self, company, owner):
        person, _ = owner
        make_project(company, person, "Live", age_days=1)
        make_project(company, person, "Old", status="archived", age_days=2)

    def test_active_is_the_default(self, owner):
        assert titles(owner[1].get(URL)) == ["Live"]

    def test_archived(self, owner):
        assert titles(owner[1].get(URL, {"status": "archived"})) == ["Old"]

    def test_all(self, owner):
        assert titles(owner[1].get(URL, {"status": "all"})) == ["Live", "Old"]

    def test_an_unknown_filter_is_refused(self, owner):
        assert owner[1].get(URL, {"status": "deleted"}).status_code == 400


class TestSearch:
    @pytest.fixture(autouse=True)
    def projects(self, company, owner):
        person, _ = owner
        for index, title in enumerate(["Backend Engineer", "Designer", "Frontend engineer"]):
            make_project(company, person, title, age_days=index)

    def test_matches_part_of_the_title_ignoring_case(self, owner):
        assert titles(owner[1].get(URL, {"search": "ENGINEER"})) == [
            "Backend Engineer",
            "Frontend engineer",
        ]

    def test_no_match_gives_nothing(self, owner):
        assert titles(owner[1].get(URL, {"search": "zzz"})) == []

    def test_percent_and_underscore_are_plain_characters(self, owner):
        assert titles(owner[1].get(URL, {"search": "%"})) == []
        assert titles(owner[1].get(URL, {"search": "_"})) == []

    def test_search_works_with_the_filter(self, company, owner):
        person, client = owner
        make_project(company, person, "Archived engineer", status="archived")
        assert titles(client.get(URL, {"search": "engineer", "status": "archived"})) == [
            "Archived engineer"
        ]

    def test_a_too_long_search_is_refused(self, owner):
        assert owner[1].get(URL, {"search": "a" * 201}).status_code == 400


class TestSort:
    @pytest.fixture(autouse=True)
    def projects(self, company, owner):
        person, _ = owner
        make_project(company, person, "banana", age_days=3)
        make_project(company, person, "Apple", age_days=1)
        make_project(company, person, "cherry", age_days=2)

    def test_last_updated_newest_first_is_the_default(self, owner):
        assert titles(owner[1].get(URL)) == ["Apple", "cherry", "banana"]

    def test_title_ignores_case(self, owner):
        assert titles(owner[1].get(URL, {"sort": "title"})) == ["Apple", "banana", "cherry"]

    def test_best_score_with_no_scores_keeps_a_stable_order(self, owner):
        assert titles(owner[1].get(URL, {"sort": "best_score"})) == ["Apple", "cherry", "banana"]

    def test_an_unknown_sort_is_refused(self, owner):
        assert owner[1].get(URL, {"sort": "random"}).status_code == 400


class TestPaging:
    @pytest.fixture(autouse=True)
    def projects(self, company, owner):
        person, _ = owner
        for index in range(45):
            make_project(company, person, f"Project {index:02d}", age_days=index)

    def test_twenty_per_page(self, owner):
        body = owner[1].get(URL).json()
        assert len(body["results"]) == 20
        assert (body["page"], body["page_size"], body["total"], body["pages"]) == (1, 20, 45, 3)

    def test_the_last_page_has_the_rest_and_no_repeats(self, owner):
        client = owner[1]
        seen = [title for page in (1, 2, 3) for title in titles(client.get(URL, {"page": page}))]
        assert len(seen) == 45
        assert len(set(seen)) == 45
        assert len(titles(client.get(URL, {"page": 3}))) == 5

    def test_a_page_past_the_end_is_empty(self, owner):
        assert owner[1].get(URL, {"page": 4}).json()["results"] == []

    @pytest.mark.parametrize("page", ["0", "-1", "x"])
    def test_a_bad_page_is_refused(self, owner, page):
        assert owner[1].get(URL, {"page": page}).status_code == 400

    def test_an_empty_page_value_means_the_first_page(self, owner):
        assert owner[1].get(URL, {"page": ""}).json()["page"] == 1

    def test_the_page_size_comes_from_platform_settings(self, owner):
        PlatformSetting.objects.create(key="projects.page_size", value=10)
        clear_cache()
        assert owner[1].get(URL).json()["pages"] == 5

    def test_paging_keeps_search_and_sort(self, owner):
        client = owner[1]
        body = client.get(URL, {"search": "Project 1", "sort": "title"}).json()
        assert body["total"] == 10
        assert titles(client.get(URL, {"search": "Project 1", "sort": "title"}))[0] == "Project 10"


def test_unknown_query_fields_are_refused(owner):
    assert owner[1].get(URL, {"company": "x"}).status_code == 400
