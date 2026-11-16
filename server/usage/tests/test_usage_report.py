import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for
from cvs.tests.test_ai_reading import set_setting
from plans.models import Subscription
from projects.models import Project
from usage import service
from usage.models import UsageCounter, UsagePeriod
from usage.report import usage_report

pytestmark = pytest.mark.django_db
URL = "/api/company/usage/history/"


def at(year, month, day, hour=0):
    return datetime(year, month, day, hour, tzinfo=UTC)


@pytest.fixture
def company():
    company = make_company()
    Subscription.objects.create(company=company, period_start=at(2030, 1, 1), state="active")
    return company


def project_of(company, title):
    owner = make_company_user(company, role="member")
    return Project.objects.create(
        company=company, title=title, job_description="t", reading_model="m", created_by=owner
    )


def use(company, project, moment, *, scored=True, tokens=(0, 0), cost="0"):
    """One CV accepted at `moment`, scored or not, with the tokens its calls used."""
    cv_id = uuid.uuid4()
    service.accept_cv(company.pk, cv_id, project.pk if project else None, now=moment)
    if scored:
        service.mark_scored(company.pk, cv_id)
    service.add_tokens(company.pk, tokens[0], tokens[1], cost, cv_id=cv_id)
    return cv_id


def client_of(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def busy(company):
    first, second = project_of(company, "Backend"), project_of(company, "Design")
    use(company, first, at(2030, 1, 7, 9), tokens=(100, 20), cost="0.5")  # a Monday
    use(company, first, at(2030, 1, 7, 9), tokens=(10, 2), cost="0.25")
    use(company, second, at(2030, 1, 12, 23), tokens=(5, 5), cost="0.1")  # a Saturday
    use(company, first, at(2030, 2, 3, 14), tokens=(7, 3), cost="0.3")  # next period
    return company, first, second


class TestPeriods:
    def test_each_period_matches_its_counters(self, busy):
        company, *_ = busy
        report = usage_report(company.pk)
        for shown in report["periods"]:
            counters = UsageCounter.objects.filter(company=company, period_id=shown["id"])
            assert shown["cvs"] == sum(c.cvs_scored for c in counters)
            assert shown["tokens_in"] == sum(c.tokens_in for c in counters)
            assert shown["tokens_out"] == sum(c.tokens_out for c in counters)
            assert Decimal(shown["estimated_cost"]) == sum(c.estimated_cost for c in counters)
            assert shown["tokens"] == shown["tokens_in"] + shown["tokens_out"]

    def test_they_match_the_usage_history_the_limits_read(self, busy):
        company, *_ = busy
        history = service.usage_history(company.pk)
        shown = usage_report(company.pk)["periods"]
        assert [h["cvs_scored"] for h in history] == [s["cvs"] for s in shown]
        assert [h["tokens_in"] + h["tokens_out"] for h in history] == [s["tokens"] for s in shown]

    def test_newest_first_with_the_period_dates(self, busy):
        company, *_ = busy
        periods = usage_report(company.pk)["periods"]
        assert [p["start"][:10] for p in periods] == ["2030-02-01", "2030-01-01"]
        assert periods[1]["end"][:10] == "2030-02-01"
        assert (periods[1]["cvs"], periods[1]["tokens"]) == (3, 142)

    def test_a_cv_that_failed_is_not_counted(self, company):
        project = project_of(company, "P")
        use(company, project, at(2030, 1, 3), scored=False, tokens=(4, 1))
        (period,) = usage_report(company.pk)["periods"]
        assert (period["cvs"], period["tokens"]) == (0, 5)

    def test_only_the_set_number_of_periods_is_listed(self, busy):
        company, *_ = busy
        set_setting("usage.history_periods", 1)
        assert len(usage_report(company.pk)["periods"]) == 1

    def test_a_company_with_no_usage_has_nothing(self, company):
        assert usage_report(company.pk) == {
            "periods": [],
            "selected": None,
            "projects": [],
            "uploads": [],
        }

    def test_another_companys_usage_is_never_included(self, busy):
        other = make_company()
        assert usage_report(other.pk)["periods"] == []


class TestProjects:
    def test_the_newest_period_is_shown_by_default(self, busy):
        company, first, _ = busy
        report = usage_report(company.pk)
        assert report["selected"] == report["periods"][0]["id"]
        assert [(p["title"], p["cvs"]) for p in report["projects"]] == [("Backend", 1)]

    def test_a_chosen_period_lists_its_projects_matching_their_counters(self, busy):
        company, first, second = busy
        january = usage_report(company.pk)["periods"][1]["id"]
        report = usage_report(company.pk, january)
        assert report["selected"] == january
        rows = {row["title"]: row for row in report["projects"]}
        assert rows["Backend"]["cvs"] == 2 and rows["Backend"]["tokens"] == 132
        assert Decimal(rows["Backend"]["estimated_cost"]) == Decimal("0.75")
        assert rows["Design"]["tokens_in"] == 5 and rows["Design"]["tokens_out"] == 5
        for row in report["projects"]:
            counter = UsageCounter.objects.get(period_id=january, project_id=row["project_id"])
            assert row["cvs"] == counter.cvs_scored
        assert [row["title"] for row in report["projects"]] == [
            "Backend",
            "Design",
        ]  # dearest first

    def test_the_projects_add_up_to_the_period(self, busy):
        company, *_ = busy
        report = usage_report(company.pk, usage_report(company.pk)["periods"][1]["id"])
        period = report["periods"][1]
        assert sum(p["cvs"] for p in report["projects"]) == period["cvs"]
        assert sum(p["tokens"] for p in report["projects"]) == period["tokens"]

    def test_a_deleted_project_keeps_its_row_without_a_title(self, busy):
        company, first, _ = busy
        Project.objects.filter(pk=first.pk).delete()
        rows = usage_report(company.pk, usage_report(company.pk)["periods"][1]["id"])["projects"]
        assert {r["title"] for r in rows} == {None, "Design"}

    def test_work_with_no_project_has_a_row_of_its_own(self, company):
        service.add_tokens(company.pk, 3, 2, "0.01", now=at(2030, 1, 5))
        (row,) = usage_report(company.pk)["projects"]
        assert row["project_id"] is None and row["tokens"] == 5

    @pytest.mark.parametrize("bad", ["nope", "00000000-0000-0000-0000-000000000000"])
    def test_an_unknown_period_is_refused(self, busy, bad):
        company, *_ = busy
        client = client_of(company)
        response = client.get(URL, {"period": bad})
        assert response.status_code == 400
        assert "period" in response.json()["error"]["fields"]

    def test_another_companys_period_is_refused(self, busy):
        company, *_ = busy
        other = make_company()
        Subscription.objects.create(company=other, period_start=at(2030, 1, 1), state="active")
        service.accept_cv(other.pk, uuid.uuid4(), None, now=at(2030, 1, 4))
        foreign = UsagePeriod.objects.get(company=other)
        response = client_of(company).get(URL, {"period": str(foreign.pk)})
        assert response.status_code == 400


class TestUploads:
    def test_uploads_are_counted_by_weekday_and_hour(self, busy):
        company, *_ = busy
        january = usage_report(company.pk)["periods"][1]["id"]
        grid = usage_report(company.pk, january)["uploads"]
        assert len(grid) == 7 and all(len(day) == 24 for day in grid)
        assert grid[0][9] == 2  # Monday 7 January, 09:00
        assert grid[5][23] == 1  # Saturday 12 January, 23:00
        assert sum(map(sum, grid)) == 3

    def test_a_cv_that_failed_still_counts_as_an_upload(self, company):
        use(company, project_of(company, "P"), at(2030, 1, 3, 4), scored=False)
        grid = usage_report(company.pk)["uploads"]
        assert grid[3][4] == 1  # Thursday

    def test_the_grid_follows_the_chosen_period(self, busy):
        company, *_ = busy
        grid = usage_report(company.pk)["uploads"]  # February
        assert sum(map(sum, grid)) == 1 and grid[6][14] == 1  # Sunday 3 February


class TestWhoMaySee:
    def test_the_owner_gets_the_report(self, busy):
        company, *_ = busy
        response = client_of(company).get(URL)
        assert response.status_code == 200
        assert len(response.json()["periods"]) == 2

    def test_a_member_is_refused(self, busy):
        company, *_ = busy
        assert client_of(company, "member").get(URL).status_code == 403

    def test_signing_in_is_needed(self):
        assert APIClient().get(URL).status_code == 401

    def test_a_company_sees_only_its_own(self, busy):
        other = make_company()
        assert client_of(other).get(URL).json()["periods"] == []
