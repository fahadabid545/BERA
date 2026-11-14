from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from cvs import recommendation, scoring
from cvs.models import AtsScore, Candidate, CandidateScore, CvContact, CvFile, CvProfile
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from usage import service as usage

pytestmark = pytest.mark.django_db
NOW = timezone.now()


@pytest.fixture
def plan():
    return make_plan()


@pytest.fixture
def tenant(plan):
    return Tenant(plan)


def add(tenant, name, score=None, *, status="done", ats=None, who="Jane Example", minutes=0):
    """A CV of the tenant's project. With a score it has a candidate; with a status of waiting,
    reading or scoring (and no score) it is still on its way."""
    row = CvFile.objects.create(
        company=tenant.company,
        project=tenant.project,
        original_name=name,
        file_type="pdf",
        size_bytes=1,
        storage_key=f"cvs/{tenant.company.pk}/{name}-{minutes}",
        content_hash=f"{name}-{minutes}-{tenant.company.pk}",
        uploaded_by=tenant.owner,
        status=status,
    )
    CvFile.objects.filter(pk=row.pk).update(created_at=NOW + timedelta(minutes=minutes))
    usage.accept_cv(tenant.company.pk, row.pk, tenant.project.pk)
    if score is None and status != "scoring":
        return row
    CvProfile.objects.create(
        company=tenant.company, cv_file=row, content={"skills": []}, model="m", prompt_version=1
    )
    CvContact.objects.create(
        company=tenant.company, cv_file=row, name=who, email="jane@example.com"
    )
    candidate = Candidate.objects.create(
        company=tenant.company,
        project=tenant.project,
        cv_file=row,
        profile=row.profile,
        contact=row.contact,
    )
    if ats is not None:
        AtsScore.objects.create(
            company=tenant.company, candidate=candidate, score=ats,
            job_description_hash="x", rules_version=1,
        )  # fmt: skip
    if score is not None:
        value = scoring.Decimal(str(score))
        CandidateScore.objects.create(
            company=tenant.company, candidate=candidate, score=value,
            grade=scoring.grade_for(value),
            label=recommendation.label_for(value, 75),
            borderline=recommendation.is_borderline(value, 75),
        )  # fmt: skip
    return row


def url(tenant, query=""):
    return f"/api/company/projects/{tenant.project.pk}/candidates/{query}"


def rows(tenant, query=""):
    response = tenant.client.get(url(tenant, query))
    assert response.status_code == 200, response.content
    return response.json()["rows"]


def names(tenant, query=""):
    return [row["file_name"] for row in rows(tenant, query)]


@pytest.fixture
def five(tenant):
    add(tenant, "c-low.pdf", 40, ats=90, minutes=1)
    add(tenant, "a-high.pdf", 90, ats=50, minutes=2)
    add(tenant, "b-mid.pdf", 70, ats=70, minutes=3)
    add(tenant, "d-top.pdf", 95, ats=10, minutes=4)
    add(tenant, "e-ok.pdf", 60, ats=None, minutes=5)
    return tenant


class TestRanking:
    def test_the_default_is_ai_score_high_to_low_with_ranks(self, five):
        shown = rows(five)
        assert [r["file_name"] for r in shown] == [
            "d-top.pdf", "a-high.pdf", "b-mid.pdf", "e-ok.pdf", "c-low.pdf",
        ]  # fmt: skip
        assert [r["rank"] for r in shown] == [1, 2, 3, 4, 5]

    def test_each_row_has_its_columns(self, five):
        top = rows(five)[0]
        assert top["score"] == "95.0" and top["grade"] == "A" and top["ats_score"] == 10
        assert (top["label"], top["stage"], top["status"]) == ("strong_match", "new", "done")
        assert top["file_name"] == "d-top.pdf" and top["added_at"]
        assert top["candidate_id"]

    def test_the_cvs_name_shows_as_initials_only(self, five):
        response = five.client.get(url(five))
        assert rows(five)[0]["name"] == "J. E."
        assert "Jane" not in response.content.decode() and "jane@" not in response.content.decode()

    def test_a_cv_not_read_yet_has_no_name(self, tenant):
        add(tenant, "new.pdf", status="waiting")
        assert rows(tenant)[0]["name"] == ""

    def test_a_tie_is_ordered_by_date_added_then_name(self, tenant):
        add(tenant, "z-late.pdf", 80, minutes=9)
        add(tenant, "b-same-time.pdf", 80, minutes=5)
        add(tenant, "a-same-time.pdf", 80, minutes=5)
        add(tenant, "first.pdf", 80, minutes=1)
        assert names(tenant) == [
            "first.pdf", "a-same-time.pdf", "b-same-time.pdf", "z-late.pdf",
        ]  # fmt: skip

    def test_the_order_is_the_same_every_time(self, tenant):
        for index in range(8):
            add(tenant, f"cv{index}.pdf", 80, minutes=index % 2)
        assert names(tenant) == names(tenant) == names(tenant, "?sort=score&direction=desc")

    def test_ties_keep_their_order_when_the_direction_flips(self, tenant):
        add(tenant, "b.pdf", 80, minutes=1)
        add(tenant, "a.pdf", 80, minutes=1)
        add(tenant, "low.pdf", 10, minutes=1)
        assert names(tenant, "?sort=score&direction=asc") == ["low.pdf", "a.pdf", "b.pdf"]

    def test_a_new_candidate_takes_its_rank_and_pushes_the_others_down(self, five):
        add(five, "newcomer.pdf", 99, ats=1, minutes=10)
        shown = rows(five)
        assert (shown[0]["file_name"], shown[0]["rank"]) == ("newcomer.pdf", 1)
        assert [r["rank"] for r in shown] == [1, 2, 3, 4, 5, 6]

    def test_the_rank_does_not_change_with_the_sort(self, five):
        by_ats = {r["file_name"]: r["rank"] for r in rows(five, "?sort=ats&direction=asc")}
        by_score = {r["file_name"]: r["rank"] for r in rows(five)}
        assert by_ats == by_score


class TestSorting:
    @pytest.mark.parametrize(
        "query,expected",
        [
            ("sort=rank&direction=asc", ["d-top", "a-high", "b-mid", "e-ok", "c-low"]),
            ("sort=rank&direction=desc", ["c-low", "e-ok", "b-mid", "a-high", "d-top"]),
            ("sort=score&direction=asc", ["c-low", "e-ok", "b-mid", "a-high", "d-top"]),
            ("sort=candidate&direction=asc", ["a-high", "b-mid", "c-low", "d-top", "e-ok"]),
            ("sort=candidate&direction=desc", ["e-ok", "d-top", "c-low", "b-mid", "a-high"]),
            ("sort=ats&direction=desc", ["c-low", "b-mid", "a-high", "d-top", "e-ok"]),
            ("sort=ats&direction=asc", ["d-top", "a-high", "b-mid", "c-low", "e-ok"]),
            ("sort=added&direction=asc", ["c-low", "a-high", "b-mid", "d-top", "e-ok"]),
            ("sort=added&direction=desc", ["e-ok", "d-top", "b-mid", "a-high", "c-low"]),
            ("sort=label&direction=asc", ["a-high", "d-top", "b-mid", "e-ok", "c-low"]),
            ("sort=label&direction=desc", ["c-low", "b-mid", "e-ok", "a-high", "d-top"]),
        ],
    )
    def test_every_column_sorts_both_ways(self, five, query, expected):
        assert [n.removesuffix(".pdf") for n in names(five, f"?{query}")] == expected

    def test_the_stage_sorts_and_ties_fall_back_to_the_tie_breakers(self, five):
        assert names(five, "?sort=stage&direction=asc") == [
            "c-low.pdf", "a-high.pdf", "b-mid.pdf", "d-top.pdf", "e-ok.pdf",
        ]  # fmt: skip

    def test_the_default_direction_of_each_column(self, five):
        assert names(five, "?sort=ats")[0] == "c-low.pdf"  # numbers: high first
        assert names(five, "?sort=candidate")[0] == "a-high.pdf"  # words: A first
        assert names(five, "?sort=added")[0] == "e-ok.pdf"  # dates: newest first

    @pytest.mark.parametrize(
        "query", ["sort=bogus", "direction=up", "page=0", "page=x", "page=-1", "sort=score;drop"]
    )
    def test_a_bad_query_is_refused_plainly(self, five, query):
        response = five.client.get(url(five, f"?{query}"))
        assert response.status_code == 400
        assert response.json()["error"]["fields"]


class TestStillProcessing:
    def test_items_on_their_way_show_their_status_and_sit_at_the_bottom(self, five):
        add(five, "waiting.pdf", status="waiting", minutes=-5)
        add(five, "reading.pdf", status="reading", minutes=-4)
        add(five, "scoring.pdf", status="scoring", minutes=-3)
        shown = rows(five)
        assert [r["file_name"] for r in shown[-3:]] == ["waiting.pdf", "reading.pdf", "scoring.pdf"]
        for row in shown[-3:]:
            assert (row["score"], row["grade"], row["rank"], row["label"]) == (
                None,
                None,
                None,
                None,
            )
        assert [r["status"] for r in shown[-3:]] == ["waiting", "reading", "scoring"]

    @pytest.mark.parametrize(
        "query",
        ["sort=score&direction=asc", "sort=candidate&direction=asc", "sort=added&direction=asc",
         "sort=ats&direction=desc", "sort=rank&direction=desc", "sort=label"],
    )  # fmt: skip
    def test_they_stay_at_the_bottom_whatever_the_sort(self, five, query):
        add(five, "aaa-waiting.pdf", status="waiting", minutes=-5)
        add(five, "zzz-reading.pdf", status="reading", minutes=99)
        assert set(names(five, f"?{query}")[-2:]) == {"aaa-waiting.pdf", "zzz-reading.pdf"}

    def test_a_candidate_being_scored_has_no_score_yet(self, five):
        add(five, "midway.pdf", status="scoring", ats=60)
        last = rows(five)[-1]
        assert last["file_name"] == "midway.pdf"
        assert (last["status"], last["score"], last["ats_score"]) == ("scoring", None, 60)

    def test_a_failed_cv_shows_its_reason(self, tenant):
        row = add(tenant, "bad.pdf", status="failed")
        CvFile.objects.filter(pk=row.pk).update(failure_reason="We could not read this file.")
        shown = rows(tenant)[0]
        assert (shown["status"], shown["reason"]) == ("failed", "We could not read this file.")

    def test_a_cancelled_cv_is_not_listed(self, five):
        add(five, "gone.pdf", status="cancelled")
        assert "gone.pdf" not in names(five)

    def test_when_it_finishes_it_takes_its_rank(self, five):
        row = add(five, "later.pdf", status="scoring", minutes=6)
        assert names(five)[-1] == "later.pdf"
        candidate = Candidate.objects.get(cv_file=row)
        CandidateScore.objects.create(
            company=five.company, candidate=candidate, score=92, grade="A", label="strong_match"
        )
        CvFile.objects.filter(pk=row.pk).update(status="done")
        assert names(five)[:3] == ["d-top.pdf", "later.pdf", "a-high.pdf"]
        assert rows(five)[1]["rank"] == 2


class TestPaging:
    @pytest.fixture
    def many(self, tenant):
        for index in range(60):
            add(tenant, f"cv{index:02d}.pdf", 100 - index, minutes=index)
        return tenant

    def test_25_to_a_page_by_default(self, many):
        body = many.client.get(url(many)).json()
        assert (len(body["rows"]), body["count"], body["pages"], body["page"]) == (25, 60, 3, 1)
        assert body["page_size"] == 25

    def test_each_page_continues_the_ranks(self, many):
        second = rows(many, "?page=2")
        assert [r["rank"] for r in second] == list(range(26, 51))
        assert [r["rank"] for r in rows(many, "?page=3")] == list(range(51, 61))

    def test_a_page_past_the_end_shows_the_last_page(self, many):
        body = many.client.get(url(many, "?page=99")).json()
        assert (body["page"], len(body["rows"])) == (3, 10)

    def test_paging_follows_the_chosen_sort(self, many):
        first = names(many, "?sort=candidate&direction=desc&page=1")
        assert first[0] == "cv59.pdf" and len(first) == 25

    def test_no_row_appears_twice_or_is_missed_across_pages(self, many):
        seen = [n for page in (1, 2, 3) for n in names(many, f"?page={page}&sort=ats")]
        assert len(seen) == len(set(seen)) == 60

    def test_the_page_size_is_a_platform_setting(self, many):
        set_setting("candidates.page_size", 10)
        body = many.client.get(url(many)).json()
        assert (len(body["rows"]), body["pages"]) == (10, 6)

    def test_an_empty_project_has_one_empty_page(self, tenant):
        body = tenant.client.get(url(tenant)).json()
        assert (body["rows"], body["count"], body["pages"], body["page"]) == ([], 0, 1, 1)

    def test_it_says_how_often_to_look_again(self, tenant):
        assert tenant.client.get(url(tenant)).json()["refresh_seconds"] == 3


class TestFastWithThousands:
    def test_the_number_of_queries_does_not_grow_with_the_rows(self, tenant):
        for index in range(30):
            add(tenant, f"cv{index}.pdf", index, ats=index)
        with CaptureQueriesContext(connection) as small:
            tenant.client.get(url(tenant, "?sort=ats"))
        bulk = 2500
        cvs = CvFile.objects.bulk_create(
            CvFile(
                company=tenant.company,
                project=tenant.project,
                original_name=f"bulk{index:05d}.pdf",
                file_type="pdf",
                size_bytes=1,
                storage_key=f"cvs/b/{index}",
                content_hash=f"b{index}",
                uploaded_by=tenant.owner,
                status="done",
            )
            for index in range(bulk)
        )  # fmt: skip
        with CaptureQueriesContext(connection) as large:
            body = tenant.client.get(url(tenant, "?sort=candidate&page=3")).json()
        assert len(large) == len(small)
        assert body["count"] == bulk + 30 and len(body["rows"]) == 25 and cvs

    def test_only_one_page_of_names_is_read(self, tenant):
        for index in range(40):
            add(tenant, f"cv{index}.pdf", index)
        body = tenant.client.get(url(tenant)).json()
        assert sum(1 for row in body["rows"] if row["name"]) == 25


class TestOnlyTheCompanysOwn:
    def test_another_companys_candidates_never_appear(self, plan, five):
        stranger = Tenant(plan)
        add(stranger, "secret-other.pdf", 99)
        assert "secret-other.pdf" not in names(five)
        assert all(r["file_name"] != "secret-other.pdf" for r in rows(five, "?page=1"))

    def test_another_companys_project_is_not_found(self, plan, five):
        stranger = Tenant(plan)
        add(stranger, "secret-other.pdf", 99)
        response = five.client.get(f"/api/company/projects/{stranger.project.pk}/candidates/")
        assert response.status_code == 404
        assert "secret-other" not in response.content.decode()

    def test_another_projects_candidates_are_not_mixed_in(self, five):
        from projects.models import Project

        other = Project.objects.create(
            company=five.company, title="Other", job_description="t", reading_model="m",
            created_by=five.owner,
        )  # fmt: skip
        mine = five.project
        five.project = other
        add(five, "in-other-project.pdf", 99)
        five.project = mine
        assert "in-other-project.pdf" not in names(five)

    def test_signed_out_is_refused(self, five):
        assert APIClient().get(url(five)).status_code == 401

    def test_staff_accounts_are_refused(self, five):
        from ai.tests.test_model_settings import admin_client

        boss, _ = admin_client("super")
        assert boss.get(url(five)).status_code in (401, 403)
