import pytest

from cvs.models import CvFile, CvProfile, RequirementResult
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add, names, url
from projects.models import Requirement

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def profile(row, **content):
    CvProfile.objects.filter(cv_file=row).update(content={"skills": [], **content})


def requirement(tenant, text, kind="must", position=1):
    return Requirement.objects.create(
        company=tenant.company, project=tenant.project, position=position, kind=kind,
        text=text, weight=5,
    )  # fmt: skip


def judge(tenant, row, item, verdict):
    RequirementResult.objects.create(
        company=tenant.company, candidate=row.candidate, requirement=item,
        requirement_text=item.text, verdict=verdict,
        evidence="" if verdict == "missing" else "quote", confidence="high",
        model="m", prompt_version=1,
    )  # fmt: skip


@pytest.fixture
def pool(tenant):
    """Four scored candidates and one CV still waiting."""
    add(tenant, "anna.pdf", 90, ats=80, minutes=1)
    add(tenant, "ben.pdf", 72, ats=60, minutes=2)
    add(tenant, "cara.pdf", 50, ats=40, minutes=3)
    add(tenant, "dan.pdf", 30, ats=None, minutes=4)
    add(tenant, "eve.pdf", status="waiting", minutes=5)
    return tenant


def get(tenant, query):
    return tenant.client.get(url(tenant, query))


class TestRanges:
    def test_score_range_keeps_the_ends(self, pool):
        assert names(pool, "?score_min=50&score_max=72") == ["ben.pdf", "cara.pdf"]

    def test_score_with_only_one_end(self, pool):
        assert names(pool, "?score_min=72") == ["anna.pdf", "ben.pdf"]
        assert names(pool, "?score_max=30") == ["dan.pdf"]

    def test_a_score_filter_leaves_out_cvs_still_on_their_way(self, pool):
        assert "eve.pdf" not in names(pool, "?score_min=0")

    def test_ats_range_leaves_out_candidates_without_an_ats_score(self, pool):
        assert names(pool, "?ats_min=40&ats_max=60") == ["ben.pdf", "cara.pdf"]
        assert "dan.pdf" not in names(pool, "?ats_min=0")

    def test_years_of_experience(self, pool):
        from cvs.models import CvFile

        for name, years in (("anna.pdf", 8.5), ("ben.pdf", 3), ("cara.pdf", None)):
            profile(CvFile.objects.get(original_name=name), years_of_experience=years)
        assert names(pool, "?years_min=3") == ["anna.pdf", "ben.pdf"]
        assert names(pool, "?years_min=4&years_max=9") == ["anna.pdf"]
        assert names(pool, "?years_max=3") == ["ben.pdf"]

    @pytest.mark.parametrize(
        "query, field",
        [
            ("score_min=abc", "score_min"),
            ("score_max=-1", "score_max"),
            ("ats_min=1.5", "ats_min"),
            ("years_max=nan", "years_max"),
            ("score_min=80&score_max=20", "score_min"),
        ],
    )
    def test_a_wrong_number_is_refused_with_the_field(self, pool, query, field):
        response = get(pool, f"?{query}")
        assert response.status_code == 400
        assert field in response.json()["error"]["fields"]


class TestChoices:
    def test_grade_takes_several(self, pool):
        assert names(pool, "?grade=A,D") == ["anna.pdf", "cara.pdf"]

    def test_label(self, pool):
        assert names(pool, "?label=strong_match") == ["anna.pdf"]

    def test_stage(self, pool):
        assert len(names(pool, "?stage=new")) == 4

    @pytest.mark.parametrize("query", ["grade=Z", "label=great", "stage=hired"])
    def test_an_unknown_choice_is_refused(self, pool, query):
        assert get(pool, f"?{query}").status_code == 400


class TestRequirements:
    def test_missing_a_must_have(self, pool):
        item = requirement(pool, "Python")
        for name, verdict in (
            ("anna.pdf", "met"),
            ("ben.pdf", "missing"),
            ("cara.pdf", "partly_met"),
        ):
            judge(pool, CvFile.objects.get(original_name=name), item, verdict)
        assert names(pool, f"?missing={item.pk}") == ["ben.pdf"]

    def test_having_a_requirement_means_it_is_met(self, pool):
        item = requirement(pool, "Python", kind="nice")
        for name, verdict in (
            ("anna.pdf", "met"),
            ("ben.pdf", "missing"),
            ("cara.pdf", "partly_met"),
        ):
            judge(pool, CvFile.objects.get(original_name=name), item, verdict)
        assert names(pool, f"?has={item.pk}") == ["anna.pdf"]

    def test_several_requirements_must_all_hold(self, pool):
        first, second = requirement(pool, "A"), requirement(pool, "B", position=2)
        anna, ben = (CvFile.objects.get(original_name=n) for n in ("anna.pdf", "ben.pdf"))
        for row in (anna, ben):
            judge(pool, row, first, "met")
        judge(pool, anna, second, "met")
        judge(pool, ben, second, "missing")
        assert names(pool, f"?has={first.pk},{second.pk}") == ["anna.pdf"]
        assert names(pool, f"?has={first.pk}&missing={second.pk}") == ["ben.pdf"]

    def test_missing_only_takes_a_must_have(self, pool):
        nice = requirement(pool, "Extra", kind="nice")
        assert get(pool, f"?missing={nice.pk}").status_code == 400

    def test_an_unknown_or_other_projects_requirement_is_refused(self, pool):
        other = Tenant(make_plan())
        foreign = requirement(other, "Theirs")
        assert get(pool, f"?has={foreign.pk}").status_code == 400
        assert get(pool, "?has=not-an-id").status_code == 400

    def test_the_answer_lists_the_projects_requirements(self, pool):
        item = requirement(pool, "Python")
        body = get(pool, "").json()
        assert body["requirements"] == [{"id": str(item.pk), "text": "Python", "kind": "must"}]


class TestDatesDuplicatesSearch:
    def test_date_added_range_includes_both_days(self, pool):
        from django.utils import timezone

        today = timezone.localdate()
        assert len(names(pool, f"?added_from={today}&added_to={today}")) == 5
        assert names(pool, "?added_to=2000-01-01") == []
        assert names(pool, "?added_from=2999-01-01") == []

    @pytest.mark.parametrize(
        "query", ["added_from=yesterday", "added_from=2026-02-02&added_to=2026-01-01"]
    )
    def test_wrong_dates_are_refused(self, pool, query):
        assert get(pool, f"?{query}").status_code == 400

    def test_duplicate_flag(self, pool):
        CvFile.objects.filter(original_name="ben.pdf").update(review=CvFile.Review.FLAGGED)
        assert names(pool, "?duplicate=true") == ["ben.pdf"]
        assert get(pool, "?duplicate=yes").status_code == 400

    def test_search_in_the_file_name_any_case(self, pool):
        assert names(pool, "?q=BEN") == ["ben.pdf"]

    def test_search_finds_cvs_still_on_their_way_by_file_name(self, pool):
        assert names(pool, "?q=eve") == ["eve.pdf"]

    def test_search_in_the_summary(self, pool):
        profile(CvFile.objects.get(original_name="cara.pdf"), summary="Builds payroll software")
        assert names(pool, "?q=Payroll") == ["cara.pdf"]

    def test_percent_and_underscore_are_plain_text(self, pool):
        assert names(pool, "?q=%25") == []
        assert names(pool, "?q=_") == []

    def test_a_search_that_is_too_long_is_refused(self, pool):
        assert get(pool, "?q=" + "a" * 201).status_code == 400


class TestCombined:
    def test_filters_combine_and_keep_the_ranking(self, pool):
        assert names(pool, "?score_min=40&ats_min=50&grade=A,B,D") == ["anna.pdf", "ben.pdf"]
        body = get(pool, "?score_min=40&ats_min=50").json()
        assert [r["rank"] for r in body["rows"]] == [1, 2]
        assert body["count"] == 2 and body["filtered"] is True

    def test_filters_work_with_sort_and_paging(self, pool):
        assert names(pool, "?grade=A,B,D&sort=score&direction=asc") == [
            "cara.pdf", "ben.pdf", "anna.pdf",
        ]  # fmt: skip
        body = get(pool, "?grade=A,B,D&page=9").json()
        assert body["page"] == 1 and body["count"] == 3

    def test_a_filter_that_matches_nothing_gives_an_empty_page(self, pool):
        body = get(pool, "?score_min=99").json()
        assert body["rows"] == [] and body["count"] == 0 and body["pages"] == 1

    def test_no_filter_is_not_filtered(self, pool):
        assert get(pool, "?q=&grade=").json()["filtered"] is False

    def test_the_filters_stay_inside_the_company(self, pool):
        other = Tenant(make_plan())
        add(other, "anna-other.pdf", 95, ats=99)
        assert "anna-other.pdf" not in names(pool, "?q=anna&score_min=0")

    def test_the_query_count_does_not_grow_with_filters_or_rows(self, pool):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        item = requirement(pool, "Python")
        query = f"?score_min=1&grade=A,B,C,D,E&missing={item.pk}&q=a&duplicate=true"
        with CaptureQueriesContext(connection) as small:
            get(pool, query)
        for number in range(20):
            add(pool, f"extra{number}.pdf", 60, ats=50, minutes=10 + number)
        with CaptureQueriesContext(connection) as large:
            get(pool, query)
        assert len(large) == len(small)
