import csv
import io
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from cvs.models import Candidate, CandidateScore, CvFile, StageChange
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add
from projects.models import Project

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def board(tenant, query=""):
    response = tenant.client.get(f"/api/company/dashboard/{query}")
    assert response.status_code == 200, response.content
    return response.json()


def behind(tenant, kind, key, query=""):
    return tenant.client.get(f"/api/company/dashboard/detail/?kind={kind}&key={key}{query}")


def stamp(row, days_ago):
    when = timezone.now() - timedelta(days=days_ago)
    CvFile.objects.filter(pk=row.pk).update(created_at=when)
    CandidateScore.objects.filter(candidate__cv_file=row).update(created_at=when)
    Candidate.objects.filter(cv_file=row).update(created_at=when)


def move(tenant, row, *stages, days_ago=0):
    previous = "new"
    for stage in stages:
        change = StageChange.objects.create(
            company=tenant.company, candidate=row.candidate, from_stage=previous,
            to_stage=stage, changed_by=tenant.owner,
        )  # fmt: skip
        StageChange.objects.filter(pk=change.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        previous = stage
    Candidate.objects.filter(pk=row.candidate.pk).update(stage=previous)


def second_project(tenant, title="Second"):
    project = Project.objects.create(
        company=tenant.company, title=title, job_description="d",
        reading_model="m", created_by=tenant.owner,
    )  # fmt: skip
    other = Tenant.__new__(Tenant)
    other.__dict__.update(tenant.__dict__)
    other.project = project
    return other


class TestPeriod:
    def test_the_default_and_the_choices_come_from_the_settings(self, tenant):
        body = board(tenant)
        assert body["days"] == 30 and body["choices"] == [1, 7, 30, 90, 180]
        set_setting("dashboard.period_choices_days", [2, 14])
        set_setting("dashboard.period_default_days", 14)
        body = board(tenant)
        assert body["days"] == 14 and body["choices"] == [2, 14]

    @pytest.mark.parametrize("days", ["0", "5", "x", "-1"])
    def test_other_periods_are_refused(self, tenant, days):
        response = tenant.client.get(f"/api/company/dashboard/?days={days}")
        assert response.status_code == 400
        assert "days" in response.json()["error"]["fields"]

    def test_the_answer_names_the_refresh_delay(self, tenant):
        assert board(tenant)["refresh_seconds"] == 3

    @pytest.mark.parametrize("days", ["90", "180"])
    def test_three_and_six_months_are_offered(self, tenant, days):
        assert board(tenant, f"?days={days}")["days"] == int(days)


class TestCounts:
    def test_an_empty_company_has_only_zeros(self, tenant):
        counts = board(tenant)["counts"]
        assert counts == {
            "projects": 1, "scored": 0, "shortlisted": 0, "interviewed": 0,
            "on_hold": 0, "selected": 0, "rejected": 0,
        }  # fmt: skip

    def test_there_is_no_comparison_with_an_earlier_period(self, tenant):
        body = board(tenant)
        assert set(body) == {
            "refresh_seconds", "days", "choices", "counts",
            "recommendations", "projects", "screening", "top",
        }  # fmt: skip

    def test_the_scored_cvs_of_the_period_only(self, tenant):
        for days_ago in (0, 1, 3):
            stamp(add(tenant, f"new{days_ago}.pdf", 80, minutes=days_ago), days_ago)
        stamp(add(tenant, "old.pdf", 60, minutes=40), 9)
        assert board(tenant, "?days=7")["counts"]["scored"] == 3
        assert board(tenant, "?days=30")["counts"]["scored"] == 4

    def test_each_flag_counts_the_candidates_put_there_in_the_period(self, tenant):
        names = ["shortlisted", "interviewed", "on_hold", "selected", "rejected"]
        for index, stage in enumerate(names):
            move(tenant, add(tenant, f"{stage}.pdf", 70, minutes=index), stage, days_ago=0)
        late = add(tenant, "late.pdf", 70, minutes=9)
        move(tenant, late, "shortlisted", days_ago=40)
        counts = board(tenant, "?days=7")["counts"]
        assert [counts[name] for name in names] == [1, 1, 1, 1, 1]
        assert board(tenant, "?days=90")["counts"]["shortlisted"] == 2

    def test_a_candidate_moved_on_is_counted_only_where_it_is_now(self, tenant):
        row = add(tenant, "a.pdf", 80)
        move(tenant, row, "shortlisted", "interviewed", days_ago=1)
        counts = board(tenant, "?days=7")["counts"]
        assert (counts["shortlisted"], counts["interviewed"]) == (0, 1)

    def test_the_projects_number_is_every_active_project_not_the_period(self, tenant):
        second_project(tenant, "Second")
        archived = second_project(tenant, "Old")
        Project.objects.filter(pk=archived.project.pk).update(status="archived")
        assert board(tenant, "?days=1")["counts"]["projects"] == 2

    def test_other_companies_are_not_counted(self, tenant):
        theirs = Tenant(make_plan())
        move(theirs, add(theirs, "theirs.pdf", 99), "selected")
        counts = board(tenant)["counts"]
        assert counts["scored"] == 0 and counts["selected"] == 0


class TestRecommendations:
    def test_counts_each_label_and_leaves_out_the_rejected(self, tenant):
        rows = [add(tenant, f"r{i}.pdf", 80, minutes=i) for i in range(4)]
        labels = ["strong_match", "possible", "possible", "not_recommended"]
        for row, label in zip(rows, labels, strict=True):
            CandidateScore.objects.filter(candidate__cv_file=row).update(label=label)
        move(tenant, rows[3], "rejected")
        found = board(tenant)["recommendations"]
        assert found["total"] == 3
        assert {p["label"]: p["count"] for p in found["parts"]} == {
            "strong_match": 1, "possible": 2, "not_recommended": 0,
        }  # fmt: skip


class TestProjectsAndScreening:
    def test_projects_are_not_started_in_progress_or_ready(self, tenant):
        busy = second_project(tenant, "Busy")
        add(busy, "waiting.pdf", status="waiting")
        add(tenant, "done.pdf", 80)
        second_project(tenant, "Empty")
        archived = second_project(tenant, "Old")
        add(archived, "x.pdf", 80, minutes=3)
        Project.objects.filter(pk=archived.project.pk).update(status="archived")
        assert board(tenant)["projects"] == {"not_started": 1, "in_progress": 1, "ready": 1}

    def test_the_share_of_cvs_that_are_scored(self, tenant):
        add(tenant, "a.pdf", 80)
        add(tenant, "b.pdf", status="waiting", minutes=1)
        add(tenant, "c.pdf", status="waiting", minutes=2)
        add(tenant, "d.pdf", 70, minutes=3)
        screening = board(tenant)["screening"]
        assert screening == {"uploaded": 4, "scored": 2, "percent": 50.0}

    def test_no_percent_before_anything_was_uploaded(self, tenant):
        assert board(tenant)["screening"]["percent"] is None


class TestTopCandidates:
    def test_the_best_candidates_of_every_project_with_their_project_and_scores(self, tenant):
        other = second_project(tenant, "Second")
        add(tenant, "a.pdf", 60, who="Jane Example")
        add(other, "b.pdf", 90, minutes=1, who="John Sample")
        top = board(tenant)["top"]
        assert [c["score"] for c in top] == ["90.0", "60.0"]
        assert [c["rank"] for c in top] == [1, 2]
        assert [c["project_title"] for c in top] == ["Second", "T"]

    def test_names_are_initials_and_the_ats_score_is_shown(self, tenant):
        add(tenant, "a.pdf", 90, who="Jane Example")
        card = board(tenant)["top"][0]
        assert card["name"] == "J. E." and card["id"] and card["project_id"]
        assert "ats_score" in card

    def test_how_many_are_shown_comes_from_the_setting(self, tenant):
        for index in range(12):
            add(tenant, f"c{index}.pdf", 50 + index, minutes=index)
        assert len(board(tenant)["top"]) == 10
        set_setting("dashboard.top_candidates_count", 2)
        assert len(board(tenant)["top"]) == 2

    def test_nobody_before_anything_is_scored(self, tenant):
        assert board(tenant)["top"] == []

    def test_rejected_candidates_are_left_out(self, tenant):
        row = add(tenant, "a.pdf", 90)
        move(tenant, row, "rejected")
        assert board(tenant)["top"] == []

    def test_other_companies_are_never_shown(self, tenant):
        add(Tenant(make_plan()), "theirs.pdf", 99)
        assert board(tenant)["top"] == []


class TestAccessAndCost:
    def test_it_needs_a_signed_in_company_user(self):
        assert APIClient().get("/api/company/dashboard/").status_code == 401
        assert (
            APIClient().get("/api/company/dashboard/detail/?kind=funnel&key=scored").status_code
            == 401
        )
        assert APIClient().get("/api/company/dashboard/report/").status_code == 401

    def test_the_query_count_does_not_grow_with_candidates(self, tenant):
        for index in range(6):
            move(tenant, add(tenant, f"s{index}.pdf", 50 + index, minutes=index), "shortlisted")
        with CaptureQueriesContext(connection) as small:
            board(tenant)
        for index in range(15):
            row = add(tenant, f"x{index}.pdf", 30 + index, minutes=20 + index)
            move(tenant, row, "shortlisted")
        with CaptureQueriesContext(connection) as large:
            board(tenant)
        assert len(large) == len(small)


class TestDetail:
    def test_a_funnel_step_lists_cvs_first_then_candidates(self, tenant):
        add(tenant, "a.pdf", 80)
        add(tenant, "b.pdf", status="waiting", minutes=1)
        uploaded = behind(tenant, "funnel", "uploaded").json()
        assert uploaded["total"] == 2 and {i["type"] for i in uploaded["items"]} == {"cv"}
        scored = behind(tenant, "funnel", "scored").json()
        item = scored["items"][0]
        assert scored["total"] == 1 and item["type"] == "candidate"
        assert item["score"] == "80.0" and item["project_title"] == "T"
        assert item["name"] == "J. E." and item["id"] and item["project_id"]

    def test_stage_steps_include_those_who_moved_on(self, tenant):
        row = add(tenant, "a.pdf", 80)
        move(tenant, row, "shortlisted", "interviewed", "rejected")
        assert behind(tenant, "funnel", "interviewed").json()["total"] == 1
        assert behind(tenant, "funnel", "selected").json()["total"] == 0

    def test_a_grade_lists_its_candidates_best_first(self, tenant):
        add(tenant, "a.pdf", 91, minutes=1)
        add(tenant, "b.pdf", 95, minutes=2)
        add(tenant, "c.pdf", 40, minutes=3)
        found = behind(tenant, "grade", "A").json()
        assert [i["score"] for i in found["items"]] == ["95.0", "91.0"]

    def test_a_label_leaves_out_the_rejected(self, tenant):
        rows = [add(tenant, f"r{i}.pdf", 80, minutes=i) for i in range(2)]
        CandidateScore.objects.update(label="strong_match")
        move(tenant, rows[1], "rejected")
        assert behind(tenant, "recommendation", "strong_match").json()["total"] == 1

    def test_the_scored_number_lists_what_the_period_counted(self, tenant):
        stamp(add(tenant, "new.pdf", 80, minutes=1), 0)
        stamp(add(tenant, "old.pdf", 80, minutes=2), 40)
        assert behind(tenant, "metric", "scored", "&days=7").json()["total"] == 1
        assert behind(tenant, "metric", "scored", "&days=90").json()["total"] == 2

    def test_a_flag_lists_its_candidates_with_the_stage_and_project(self, tenant):
        row = add(tenant, "a.pdf", 80)
        move(tenant, row, "on_hold", days_ago=0)
        late = add(tenant, "b.pdf", 70, minutes=1)
        move(tenant, late, "on_hold", days_ago=20)
        found = behind(tenant, "stage", "on_hold", "&days=7").json()
        assert found["total"] == 1
        item = found["items"][0]
        assert item["stage"] == "on_hold" and item["project_id"] and item["id"]
        assert behind(tenant, "stage", "on_hold", "&days=30").json()["total"] == 2

    def test_a_flag_never_lists_another_companys_candidates(self, tenant):
        theirs = Tenant(make_plan())
        move(theirs, add(theirs, "theirs.pdf", 99), "selected")
        assert behind(tenant, "stage", "selected").json()["total"] == 0

    def test_project_groups_list_projects_with_their_counts(self, tenant):
        add(tenant, "a.pdf", 80)
        add(tenant, "b.pdf", status="failed", minutes=1)
        found = behind(tenant, "project_status", "ready").json()
        assert found["total"] == 1
        item = found["items"][0]
        assert item["type"] == "project" and item["title"] == "T"
        assert (item["cvs"], item["scored"], item["failed"]) == (2, 1, 1)

    def test_screening_lists_every_active_project(self, tenant):
        second_project(tenant)
        assert behind(tenant, "screening", "all").json()["total"] == 2

    def test_the_list_is_cut_at_the_setting_but_the_total_is_real(self, tenant):
        for index in range(5):
            add(tenant, f"c{index}.pdf", 50 + index, minutes=index)
        set_setting("dashboard.detail_limit", 2)
        found = behind(tenant, "funnel", "scored").json()
        assert found["total"] == 5 and len(found["items"]) == 2

    def test_nothing_of_other_companies(self, tenant):
        add(Tenant(make_plan()), "theirs.pdf", 99)
        for kind, key in (("funnel", "uploaded"), ("funnel", "scored"), ("grade", "A")):
            assert behind(tenant, kind, key).json()["total"] == 0

    @pytest.mark.parametrize(
        ("kind", "key"),
        [("nope", "x"), ("funnel", "nope"), ("grade", ""), ("recommendation", "nope"),
         ("project_status", "nope"), ("stage", "new"), ("metric", "nope"), ("", "")],
    )  # fmt: skip
    def test_unknown_things_are_refused(self, tenant, kind, key):
        response = behind(tenant, kind, key)
        assert response.status_code == 400
        assert "kind" in response.json()["error"]["fields"]

    def test_the_period_is_checked(self, tenant):
        assert behind(tenant, "metric", "scored", "&days=5").status_code == 400

    def test_a_project_can_narrow_the_funnel_and_grades(self, tenant):
        other = second_project(tenant)
        add(tenant, "a.pdf", 91, minutes=1)
        add(other, "b.pdf", 95, minutes=2)
        both = behind(tenant, "funnel", "scored").json()
        mine = behind(tenant, "funnel", "scored", f"&project={tenant.project.pk}").json()
        assert both["total"] == 2 and mine["total"] == 1
        assert (
            behind(tenant, "funnel", "uploaded", f"&project={other.project.pk}").json()["total"]
            == 1
        )
        assert behind(tenant, "grade", "A", f"&project={other.project.pk}").json()["total"] == 1

    def test_a_project_of_another_company_or_a_bad_id_is_not_found(self, tenant):
        theirs = Tenant(make_plan())
        for value in (theirs.project.pk, "nope"):
            assert behind(tenant, "funnel", "scored", f"&project={value}").status_code == 404


class TestReport:
    def test_the_numbers_as_a_table(self, tenant):
        add(tenant, "a.pdf", 80, minutes=1)
        add(tenant, "b.pdf", 60, minutes=2)
        CandidateScore.objects.filter(candidate__cv_file__original_name="a.pdf").update(
            label="strong_match"
        )
        body = tenant.client.get("/api/company/dashboard/report/?days=7").json()
        assert body["days"] == 7
        summary = {row["metric"]: row["count"] for row in body["summary"]}
        assert summary["CVs scored"] == 2 and summary["Projects"] == 1
        assert list(summary) == [
            "Projects", "CVs scored", "Shortlisted", "Interviewed",
            "On hold", "Selected", "Rejected",
        ]  # fmt: skip
        assert body["projects"] == [
            {"project": "T", "cvs": 2, "scored": 2, "strong_matches": 1, "average_score": 70.0}
        ]

    def test_the_file_is_csv_without_candidate_names(self, tenant):
        add(tenant, "a.pdf", 80, who="Jane Example")
        response = tenant.client.get("/api/company/dashboard/report/?as=csv")
        assert response["Content-Type"].startswith("text/csv")
        assert "attachment" in response["Content-Disposition"]
        text = response.content.decode()
        assert "Jane" not in text and "Example" not in text and "a.pdf" not in text
        rows = list(csv.reader(io.StringIO(text)))
        assert ["Metric", "Count"] in rows
        assert ["Project", "CVs", "Scored", "Strong matches", "Average AI score"] in rows
        assert ["T", "1", "1", "1", "80.0"] in rows

    def test_a_title_that_looks_like_a_formula_is_made_safe(self, tenant):
        Project.objects.filter(pk=tenant.project.pk).update(title="=HYPERLINK(1)")
        text = tenant.client.get("/api/company/dashboard/report/?as=csv").content.decode()
        assert "'=HYPERLINK(1)" in text and "\n=HYPERLINK" not in text

    def test_the_period_is_checked(self, tenant):
        assert tenant.client.get("/api/company/dashboard/report/?days=5").status_code == 400
