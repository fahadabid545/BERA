import csv
import io
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from cvs.models import Candidate, CandidateScore, CvFile, SharedReport, StageChange
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
        assert body["days"] == 30 and body["choices"] == [1, 7, 30]
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


class TestCards:
    def test_an_empty_company_has_zeros_and_no_averages(self, tenant):
        cards = board(tenant)["cards"]
        assert cards["uploaded"]["value"] == 0 and cards["uploaded"]["change"] is None
        assert cards["average_score"]["value"] is None
        assert cards["average_score"]["series"] == [0] * 7

    def test_this_period_against_the_one_before(self, tenant):
        for days_ago in (0, 1, 3):
            stamp(add(tenant, f"new{days_ago}.pdf", 80, minutes=days_ago), days_ago)
        stamp(add(tenant, "old.pdf", 60, minutes=40), 9)
        stamp(add(tenant, "ancient.pdf", 60, minutes=41), 80)
        cards = board(tenant, "?days=7")["cards"]
        assert (cards["uploaded"]["value"], cards["uploaded"]["previous"]) == (3, 1)
        assert cards["uploaded"]["change"] == 200.0
        assert (cards["scored"]["value"], cards["scored"]["previous"]) == (3, 1)

    def test_the_sparkline_has_one_value_for_each_day_from_the_setting(self, tenant):
        stamp(add(tenant, "today.pdf", 80), 0)
        series = board(tenant)["cards"]["uploaded"]["series"]
        assert len(series) == 7 and series[-1] == 1
        set_setting("dashboard.sparkline_days", 3)
        assert len(board(tenant)["cards"]["uploaded"]["series"]) == 3

    def test_a_candidate_shortlisted_twice_counts_once_on_the_first_day(self, tenant):
        row = add(tenant, "a.pdf", 80)
        move(tenant, row, "shortlisted", days_ago=2)
        move(tenant, row, "interviewed", days_ago=1)
        move(tenant, row, "shortlisted", days_ago=0)
        cards = board(tenant, "?days=7")["cards"]
        assert cards["shortlisted"]["value"] == 1
        assert board(tenant, "?days=1")["cards"]["shortlisted"]["value"] == 0

    def test_the_average_score_and_its_change_in_points(self, tenant):
        stamp(add(tenant, "a.pdf", 80, minutes=1), 0)
        stamp(add(tenant, "b.pdf", 60, minutes=2), 1)
        stamp(add(tenant, "c.pdf", 50, minutes=3), 9)
        card = board(tenant, "?days=7")["cards"]["average_score"]
        assert (card["value"], card["previous"], card["change"]) == (70.0, 50.0, 20.0)
        assert card["series"][-1] == 80.0 and card["series"][-2] == 60.0

    def test_other_companies_are_not_counted(self, tenant):
        theirs = Tenant(make_plan())
        add(theirs, "theirs.pdf", 99)
        assert board(tenant)["cards"]["uploaded"]["value"] == 0


class TestInsights:
    def test_the_hiring_pace_is_the_upload_change(self, tenant):
        stamp(add(tenant, "a.pdf", 50, minutes=1), 0)
        stamp(add(tenant, "b.pdf", 50, minutes=2), 1)
        stamp(add(tenant, "c.pdf", 50, minutes=3), 9)
        pace = board(tenant, "?days=7")["insights"]["hiring_pace"]
        assert (pace["current"], pace["previous"], pace["change"]) == (2, 1, 100.0)

    def test_the_share_of_strong_matches_against_before(self, tenant):
        rows = [add(tenant, f"n{i}.pdf", 80, minutes=i) for i in range(4)]
        rows += [add(tenant, f"o{i}.pdf", 80, minutes=10 + i) for i in range(2)]
        for row in rows:
            stamp(row, 0 if rows.index(row) < 4 else 9)
        CandidateScore.objects.filter(candidate__cv_file=rows[0]).update(label="strong_match")
        CandidateScore.objects.filter(candidate__cv_file=rows[4]).update(label="strong_match")
        CandidateScore.objects.filter(candidate__cv_file__in=rows[1:4] + rows[5:]).update(
            label="possible"
        )
        quality = board(tenant, "?days=7")["insights"]["match_quality"]
        assert (quality["share"], quality["previous_share"], quality["change"]) == (
            25.0,
            50.0,
            -25.0,
        )

    def test_no_share_when_nothing_was_scored(self, tenant):
        quality = board(tenant)["insights"]["match_quality"]
        assert quality["share"] is None and quality["change"] is None

    def test_the_median_hours_from_added_to_shortlisted(self, tenant):
        for index, hours in enumerate((2, 4, 30)):
            row = add(tenant, f"s{index}.pdf", 80, minutes=index)
            added = timezone.now() - timedelta(hours=hours + 1)
            Candidate.objects.filter(cv_file=row).update(created_at=added)
            move(tenant, row, "shortlisted")
            StageChange.objects.filter(candidate=row.candidate).update(
                created_at=added + timedelta(hours=hours)
            )
        assert board(tenant, "?days=7")["insights"]["time_to_shortlist"]["hours"] == 4.0

    def test_no_hours_when_nobody_was_shortlisted(self, tenant):
        add(tenant, "a.pdf", 80)
        assert board(tenant)["insights"]["time_to_shortlist"]["hours"] is None


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
    def test_the_best_candidates_of_the_most_recent_project_with_scores(self, tenant):
        for index, score in enumerate((60, 90, 75)):
            add(tenant, f"c{index}.pdf", score, minutes=index, who="Jane Example")
        top = board(tenant)["top"]
        assert top["project_id"] == str(tenant.project.pk)
        assert [c["score"] for c in top["candidates"]] == ["90.0", "75.0", "60.0"]
        assert [c["rank"] for c in top["candidates"]] == [1, 2, 3]

    def test_names_are_initials_and_strengths_are_cut_short(self, tenant):
        add(tenant, "a.pdf", 90, who="Jane Example")
        CandidateScore.objects.update(strengths=["one", "two", "three"])
        card = board(tenant)["top"]["candidates"][0]
        assert card["name"] == "J. E." and card["strengths"] == ["one", "two"]
        assert card["project_title"] == "T" and card["id"] and card["project_id"]

    def test_how_many_are_shown_comes_from_the_setting(self, tenant):
        for index in range(7):
            add(tenant, f"c{index}.pdf", 50 + index, minutes=index)
        assert len(board(tenant)["top"]["candidates"]) == 5
        set_setting("dashboard.top_candidates_count", 2)
        assert len(board(tenant)["top"]["candidates"]) == 2

    def test_another_project_can_be_chosen(self, tenant):
        other = second_project(tenant)
        add(tenant, "a.pdf", 90)
        add(other, "b.pdf", 40, minutes=5)
        top = board(tenant, f"?project={other.project.pk}")["top"]
        assert top["project_id"] == str(other.project.pk)
        assert [c["score"] for c in top["candidates"]] == ["40.0"]
        assert {p["title"] for p in top["projects"]} == {"T", "Second"}

    def test_the_compare_limits_come_from_the_settings(self, tenant):
        assert board(tenant)["top"]["compare_limits"] == {"min": 2, "max": 4}
        set_setting("comparison.max_candidates", 3)
        assert board(tenant)["top"]["compare_limits"]["max"] == 3

    def test_no_candidates_before_anything_is_scored(self, tenant):
        top = board(tenant)["top"]
        assert top["candidates"] == [] and top["project_id"] is None

    def test_a_project_of_another_company_or_a_bad_id_is_not_found(self, tenant):
        theirs = Tenant(make_plan())
        for value in (theirs.project.pk, "not-an-id"):
            response = tenant.client.get(f"/api/company/dashboard/?project={value}")
            assert response.status_code == 404

    def test_rejected_candidates_are_left_out(self, tenant):
        row = add(tenant, "a.pdf", 90)
        move(tenant, row, "rejected")
        assert board(tenant)["top"]["candidates"] == []


class TestPendingAndActivity:
    def test_counts_what_waits_for_the_person(self, tenant):
        add(tenant, "a.pdf", status="awaiting_confirmation", minutes=1)
        add(tenant, "b.pdf", status="awaiting_confirmation", minutes=2)
        add(tenant, "c.pdf", status="failed", minutes=3)
        add(tenant, "d.pdf", 80, minutes=4)
        pending = board(tenant)["pending"]
        assert pending["awaiting_confirmation"] == 2 and pending["failed"] == 1

    def share(self, tenant, days, **fields):
        return SharedReport.objects.create(
            company=tenant.company, project=tenant.project, created_by=tenant.owner,
            token_hash=f"hash-{days}-{len(fields)}-{id(fields)}", project_title="T",
            entries=[], contacts="", hide_contact=True,
            expires_at=timezone.now() + timedelta(days=days), **fields,
        )  # fmt: skip

    def test_links_that_end_soon_are_counted_not_revoked_or_ended_ones(self, tenant):
        self.share(tenant, 2)
        self.share(tenant, 30)
        self.share(tenant, -1)
        self.share(tenant, 1, revoked_at=timezone.now())
        assert board(tenant)["pending"]["links_expiring"] == 1
        set_setting("dashboard.expiring_link_days", 60)
        assert board(tenant)["pending"]["links_expiring"] == 2

    def test_the_newest_events_first_up_to_the_limit(self, tenant):
        rows = [add(tenant, f"c{i}.pdf", 70, minutes=i) for i in range(3)]
        for index, row in enumerate(rows):
            stamp(row, 3 - index)
        move(tenant, rows[0], "shortlisted", days_ago=0)
        events = board(tenant)["activity"]
        assert events[0]["kind"] == "moved" and events[0]["to_stage"] == "shortlisted"
        assert {event["kind"] for event in events} == {"moved", "scored"}
        times = [event["at"] for event in events]
        assert times == sorted(times, reverse=True)
        set_setting("dashboard.activity_limit", 2)
        assert len(board(tenant)["activity"]) == 2

    def test_a_shared_report_shows_without_a_name(self, tenant):
        self.share(tenant, 5)
        event = board(tenant)["activity"][0]
        assert event["kind"] == "shared" and event["project_title"] == "T"
        assert "name" not in event

    def test_only_this_companys_events(self, tenant):
        add(Tenant(make_plan()), "theirs.pdf", 99)
        assert board(tenant)["activity"] == []


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

    def test_a_card_lists_what_the_period_counted(self, tenant):
        stamp(add(tenant, "new.pdf", 80, minutes=1), 0)
        stamp(add(tenant, "old.pdf", 80, minutes=2), 40)
        assert behind(tenant, "metric", "uploaded", "&days=7").json()["total"] == 1
        assert behind(tenant, "metric", "scored", "&days=7").json()["total"] == 1
        assert behind(tenant, "metric", "scored", "&days=30").json()["total"] == 1

    def test_the_shortlisted_card_lists_those_shortlisted_in_the_period(self, tenant):
        row = add(tenant, "a.pdf", 80)
        move(tenant, row, "shortlisted", days_ago=0)
        late = add(tenant, "b.pdf", 70, minutes=1)
        move(tenant, late, "shortlisted", days_ago=20)
        assert behind(tenant, "metric", "shortlisted", "&days=7").json()["total"] == 1
        assert behind(tenant, "insight", "time_to_shortlist", "&days=30").json()["total"] == 2

    def test_the_strong_match_insight_lists_strong_matches_of_the_period(self, tenant):
        add(tenant, "a.pdf", 80, minutes=1)
        add(tenant, "b.pdf", 80, minutes=2)
        CandidateScore.objects.filter(candidate__cv_file__original_name="b.pdf").update(
            label="possible"
        )
        assert behind(tenant, "insight", "match_quality", "&days=7").json()["total"] == 1

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

    def test_pending_cvs_and_links(self, tenant):
        add(tenant, "a.pdf", status="awaiting_confirmation")
        add(tenant, "b.pdf", status="failed", minutes=1)
        assert behind(tenant, "pending", "awaiting_confirmation").json()["total"] == 1
        failed = behind(tenant, "pending", "failed").json()["items"][0]
        assert failed["type"] == "cv" and failed["status"] == "failed"
        TestPendingAndActivity().share(tenant, 1)
        links = behind(tenant, "pending", "links_expiring").json()
        assert links["total"] == 1 and links["items"][0]["type"] == "report"

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
         ("project_status", "nope"), ("pending", "nope"), ("metric", "nope"), ("", "")],
    )  # fmt: skip
    def test_unknown_things_are_refused(self, tenant, kind, key):
        response = behind(tenant, kind, key)
        assert response.status_code == 400
        assert "kind" in response.json()["error"]["fields"]

    def test_the_period_is_checked(self, tenant):
        assert behind(tenant, "metric", "uploaded", "&days=5").status_code == 400

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
        summary = {row["metric"]: row for row in body["summary"]}
        assert summary["CVs uploaded"]["current"] == 2
        assert summary["Average AI score"]["current"] == 70.0
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
        assert ["Project", "CVs", "Scored", "Strong matches", "Average AI score"] in rows
        assert ["T", "1", "1", "1", "80.0"] in rows

    def test_a_title_that_looks_like_a_formula_is_made_safe(self, tenant):
        Project.objects.filter(pk=tenant.project.pk).update(title="=HYPERLINK(1)")
        text = tenant.client.get("/api/company/dashboard/report/?as=csv").content.decode()
        assert "'=HYPERLINK(1)" in text and "\n=HYPERLINK" not in text

    def test_the_period_is_checked(self, tenant):
        assert tenant.client.get("/api/company/dashboard/report/?days=5").status_code == 400
