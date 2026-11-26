from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from cvs.models import Candidate, CandidateScore, CvFile, RequirementResult, StageChange
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add
from projects.models import ProjectScoringSettings, Requirement

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def charts(tenant, query=""):
    return tenant.client.get(f"/api/company/projects/{tenant.project.pk}/charts/{query}")


def company(tenant, query=""):
    return tenant.client.get(f"/api/company/charts/{query}")


def counts(body, key="funnel"):
    return {item["step"]: item["count"] for item in body[key]}


def move(tenant, row, *stages):
    previous = "new"
    for stage in stages:
        StageChange.objects.create(
            company=tenant.company, candidate=row.candidate, from_stage=previous,
            to_stage=stage, changed_by=tenant.owner,
        )  # fmt: skip
        previous = stage
    Candidate.objects.filter(pk=row.candidate.pk).update(stage=previous)


class TestFunnel:
    def test_an_empty_project_has_zero_everywhere(self, tenant):
        body = charts(tenant).json()
        assert [item["step"] for item in body["funnel"]] == [
            "uploaded", "read", "scored", "shortlisted", "interviewed", "selected",
        ]  # fmt: skip
        assert set(counts(body).values()) == {0}

    def test_each_step_counts_what_reached_it(self, tenant):
        rows = [add(tenant, f"cv{n}.pdf", 50 + n, minutes=n) for n in range(4)]
        add(tenant, "reading.pdf", status="reading", minutes=9)
        add(tenant, "scoring.pdf", status="scoring", minutes=10)
        move(tenant, rows[0], "shortlisted", "interviewed", "selected")
        move(tenant, rows[1], "shortlisted", "interviewed")
        move(tenant, rows[2], "shortlisted")
        assert counts(charts(tenant).json()) == {
            "uploaded": 6, "read": 5, "scored": 4,
            "shortlisted": 3, "interviewed": 2, "selected": 1,
        }  # fmt: skip

    def test_a_candidate_rejected_later_still_counts_for_what_it_reached(self, tenant):
        row = add(tenant, "cv.pdf", 60)
        move(tenant, row, "shortlisted", "interviewed", "rejected")
        assert counts(charts(tenant).json())["interviewed"] == 1

    def test_skipping_a_stage_still_counts_the_earlier_ones(self, tenant):
        row = add(tenant, "cv.pdf", 60)
        move(tenant, row, "selected")
        found = counts(charts(tenant).json())
        assert (found["shortlisted"], found["interviewed"], found["selected"]) == (1, 1, 1)

    def test_every_step_is_a_part_of_the_one_before(self, tenant):
        rows = [add(tenant, f"cv{n}.pdf", 50, minutes=n) for n in range(3)]
        add(tenant, "waiting.pdf", status="waiting", minutes=9)
        move(tenant, rows[0], "selected")
        move(tenant, rows[1], "shortlisted", "rejected")
        values = [item["count"] for item in charts(tenant).json()["funnel"]]
        assert values == sorted(values, reverse=True)

    def test_cancelled_uploads_are_not_counted_and_a_stage_without_score_is_not(self, tenant):
        add(tenant, "cancelled.pdf", status="cancelled", minutes=1)
        row = add(tenant, "scoring.pdf", status="scoring", minutes=2)
        move(tenant, row, "shortlisted")
        found = counts(charts(tenant).json())
        assert found["uploaded"] == 1 and found["scored"] == 0 and found["shortlisted"] == 0


class TestDistribution:
    def test_every_grade_is_listed_with_its_count(self, tenant):
        for number, score in enumerate([95, 92, 75, 60, 10]):
            add(tenant, f"cv{number}.pdf", score, minutes=number)
        shown = {item["grade"]: item["count"] for item in charts(tenant).json()["distribution"]}
        assert list(shown) == ["A", "B", "C", "D", "E"]
        assert sum(shown.values()) == 5 and shown["E"] == 1

    def test_no_candidates_gives_zero_for_every_grade(self, tenant):
        assert {i["count"] for i in charts(tenant).json()["distribution"]} == {0}


class TestRanking:
    def test_best_first_with_masked_names(self, tenant):
        add(tenant, "low.pdf", 40, minutes=1)
        add(tenant, "high.pdf", 90, minutes=2)
        shown = charts(tenant).json()["ranking"]
        assert [i["file_name"] for i in shown] == ["high.pdf", "low.pdf"]
        assert [i["rank"] for i in shown] == [1, 2]
        assert shown[0]["name"] == "J. E." and shown[0]["score"] == "90.0"

    def test_it_follows_the_top_list_size_and_the_bar_limit(self, tenant):
        for number in range(12):
            add(tenant, f"cv{number}.pdf", 10 + number, minutes=number)
        ProjectScoringSettings.objects.create(
            company_id=tenant.company.pk, project=tenant.project, must_weight_percent=70,
            nice_weight_percent=30, recommendation_threshold=75, top_n=3,
            cap_on_missing_must_have=True,
        )  # fmt: skip
        assert len(charts(tenant).json()["ranking"]) == 3
        ProjectScoringSettings.objects.update(top_n=11)
        assert len(charts(tenant).json()["ranking"]) == 10
        set_setting("charts.ranking_max_bars", 4)
        assert len(charts(tenant).json()["ranking"]) == 4

    def test_rejected_candidates_are_not_in_it(self, tenant):
        row = add(tenant, "gone.pdf", 99)
        add(tenant, "kept.pdf", 50, minutes=1)
        Candidate.objects.filter(pk=row.candidate.pk).update(stage="rejected")
        assert [i["file_name"] for i in charts(tenant).json()["ranking"]] == ["kept.pdf"]


class TestCoverage:
    def judge(self, tenant, row, item, verdict, text=None):
        RequirementResult.objects.create(
            company=tenant.company, candidate=row.candidate, requirement=item,
            requirement_text=text or item.text, verdict=verdict,
            evidence="" if verdict == "missing" else "q", confidence="high",
            model="m", prompt_version=1,
        )  # fmt: skip

    def test_counts_each_verdict_and_what_is_not_judged_yet(self, tenant):
        item = Requirement.objects.create(
            company=tenant.company, project=tenant.project, position=1, kind="must",
            text="Python", weight=5,
        )  # fmt: skip
        rows = [add(tenant, f"cv{n}.pdf", 50, minutes=n) for n in range(5)]
        self.judge(tenant, rows[0], item, "met")
        self.judge(tenant, rows[1], item, "met")
        self.judge(tenant, rows[2], item, "partly_met")
        self.judge(tenant, rows[3], item, "missing")
        body = charts(tenant).json()["coverage"]
        assert body["candidates"] == 5
        assert body["requirements"][0] | {"requirement_id": ""} == {
            "requirement_id": "", "text": "Python", "kind": "must",
            "met": 2, "partly_met": 1, "missing": 1, "not_judged": 1,
        }  # fmt: skip

    def test_a_verdict_for_older_wording_is_not_counted(self, tenant):
        item = Requirement.objects.create(
            company=tenant.company, project=tenant.project, position=1, kind="nice",
            text="Python 3", weight=2,
        )  # fmt: skip
        row = add(tenant, "cv.pdf", 50)
        self.judge(tenant, row, item, "met", text="Python")
        entry = charts(tenant).json()["coverage"]["requirements"][0]
        assert entry["met"] == 0 and entry["not_judged"] == 1

    def test_no_requirements_gives_an_empty_list(self, tenant):
        add(tenant, "cv.pdf", 50)
        assert charts(tenant).json()["coverage"] == {"candidates": 1, "requirements": []}


class TestTrend:
    def stamp(self, row, days_ago):
        when = timezone.now() - timedelta(days=days_ago)
        CvFile.objects.filter(pk=row.pk).update(created_at=when)
        CandidateScore.objects.filter(candidate__cv_file=row).update(created_at=when)

    def test_this_period_against_the_one_before_with_the_change(self, tenant):
        for number, days_ago in enumerate((0, 0, 1, 6)):
            # A running number keeps same-day files apart (a memory address can repeat).
            self.stamp(add(tenant, f"now{days_ago}-{number}.pdf", 50, minutes=days_ago), days_ago)
        for days_ago in (7, 9):
            self.stamp(add(tenant, f"old{days_ago}.pdf", 50, minutes=30 + days_ago), days_ago)
        self.stamp(add(tenant, "ancient.pdf", 50, minutes=99), 20)
        metric = charts(tenant).json()["trend"]["metrics"]["uploaded"]
        assert len(metric["current"]) == 7 and len(metric["previous"]) == 7
        assert (
            metric["current"][-1] == 2 and metric["current"][-2] == 1 and metric["current"][0] == 1
        )
        assert (metric["total"], metric["previous_total"]) == (4, 2)
        assert metric["change_percent"] == 100.0
        assert charts(tenant).json()["trend"]["metrics"]["scored"]["total"] == 4

    def test_no_change_figure_when_there_was_nothing_before(self, tenant):
        add(tenant, "cv.pdf", 50)
        metric = charts(tenant).json()["trend"]["metrics"]["uploaded"]
        assert metric["previous_total"] == 0 and metric["change_percent"] is None

    def test_a_drop_is_negative(self, tenant):
        self.stamp(add(tenant, "a.pdf", 50, minutes=1), 0)
        for number in range(4):
            self.stamp(add(tenant, f"b{number}.pdf", 50, minutes=2 + number), 8)
        assert charts(tenant).json()["trend"]["metrics"]["uploaded"]["change_percent"] == -75.0

    @pytest.mark.parametrize("days", [7, 30, 90])
    def test_the_offered_periods(self, tenant, days):
        body = charts(tenant, f"?days={days}").json()["trend"]
        assert body["days"] == days and len(body["metrics"]["scored"]["current"]) == days

    @pytest.mark.parametrize("days", ["8", "0", "-7", "abc", "7.5"])
    def test_other_periods_are_refused(self, tenant, days):
        response = charts(tenant, f"?days={days}")
        assert response.status_code == 400 and "days" in response.json()["error"]["fields"]

    def test_the_choices_and_default_come_from_the_settings(self, tenant):
        set_setting("charts.trend_days_choices", [14])
        set_setting("charts.trend_days_default", 14)
        body = charts(tenant).json()["trend"]
        assert body["days"] == 14 and body["choices"] == [14]
        assert charts(tenant, "?days=7").status_code == 400


class TestCompany:
    def test_adds_up_all_the_companys_projects_and_nobody_elses(self, tenant):
        from projects.models import Project

        add(tenant, "mine.pdf", 90)
        second = Project.objects.create(
            company=tenant.company, title="Second", job_description="d",
            reading_model="m", created_by=tenant.owner,
        )  # fmt: skip
        other_project = Tenant.__new__(Tenant)
        other_project.__dict__.update(tenant.__dict__)
        other_project.project = second
        add(other_project, "second.pdf", 40, minutes=5)
        theirs = Tenant(make_plan())
        add(theirs, "theirs.pdf", 99)
        body = company(tenant).json()
        assert counts(body)["uploaded"] == 2 and counts(body)["scored"] == 2
        assert sum(i["count"] for i in body["distribution"]) == 2
        assert body["trend"]["metrics"]["uploaded"]["total"] == 2
        assert "ranking" not in body and "coverage" not in body

    def test_it_needs_a_signed_in_company_user(self, tenant):
        from rest_framework.test import APIClient

        assert APIClient().get("/api/company/charts/").status_code == 401


class TestProjectCharts:
    def test_only_the_projects_own_data_and_company(self, tenant):
        add(tenant, "mine.pdf", 90)
        other = Tenant(make_plan())
        add(other, "theirs.pdf", 99)
        assert counts(charts(tenant).json())["scored"] == 1
        assert charts(other).json()["ranking"][0]["file_name"] == "theirs.pdf"
        foreign = f"/api/company/projects/{other.project.pk}/charts/"
        assert tenant.client.get(foreign).status_code == 404

    def test_the_answer_names_the_refresh_delay(self, tenant):
        assert charts(tenant).json()["refresh_seconds"] == 3

    def test_the_query_count_does_not_grow_with_candidates(self, tenant):
        add(tenant, "a.pdf", 50)
        with CaptureQueriesContext(connection) as small:
            charts(tenant)
        for number in range(15):
            row = add(tenant, f"x{number}.pdf", 30 + number, minutes=10 + number)
            move(tenant, row, "shortlisted")
        with CaptureQueriesContext(connection) as large:
            charts(tenant)
        assert len(large) == len(small)
