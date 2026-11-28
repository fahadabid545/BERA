from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import ActivityEntry
from core.tests.factories import make_company_user, start_session_for
from cvs.models import Candidate, CandidateScore, CvContact, SharedReport
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add
from projects.models import Project, ProjectScoringSettings

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def base(tenant):
    return f"/api/company/projects/{tenant.project.pk}/reports/"


def share(tenant, client=None, **body):
    return (client or tenant.client).post(base(tenant), body, format="json")


def public(token):
    return APIClient().get(f"/api/reports/{token}/")


def top_n(tenant, value):
    ProjectScoringSettings.objects.update_or_create(
        project=tenant.project,
        defaults={
            "company_id": tenant.company.pk, "must_weight_percent": 70, "nice_weight_percent": 30,
            "recommendation_threshold": 75, "top_n": value, "cap_on_missing_must_have": True,
        },
    )  # fmt: skip


@pytest.fixture
def pool(tenant):
    top_n(tenant, 2)
    first = add(tenant, "anna.pdf", 90, minutes=1, who="Anna Example")
    second = add(tenant, "ben.pdf", 80, minutes=2, who="Ben Example")
    add(tenant, "cara.pdf", 50, minutes=3, who="Cara Example")
    CandidateScore.objects.filter(candidate=first.candidate).update(
        strengths=["Strong Python"], risks=["Short tenure"]
    )
    CvContact.objects.filter(cv_file=second).update(phone="+1 555 0100")
    return tenant


class TestCreate:
    def test_makes_a_link_for_the_current_top_with_the_default_expiry(self, pool):
        response = share(pool)
        assert response.status_code == 201
        body = response.json()
        assert len(body["token"]) >= 40
        assert body["candidates"] == 2 and body["status"] == "active" and body["views"] == 0
        assert body["hide_contact"] is False
        days = (SharedReport.objects.get().expires_at - timezone.now()).total_seconds() / 86400
        assert 6.9 < days <= 7

    @pytest.mark.parametrize("days", [1, 7, 30])
    def test_the_offered_times(self, pool, days):
        assert share(pool, days=days).status_code == 201
        left = SharedReport.objects.get().expires_at - timezone.now()
        assert timedelta(days=days) - timedelta(minutes=1) < left <= timedelta(days=days)

    @pytest.mark.parametrize("days", [2, 0, -1, "7", True, 365])
    def test_other_times_are_refused(self, pool, days):
        response = share(pool, days=days)
        assert response.status_code == 400 and "days" in response.json()["error"]["fields"]
        assert SharedReport.objects.count() == 0

    def test_the_choices_come_from_the_settings(self, pool):
        set_setting("sharing.report_link_choices_days", [3])
        set_setting("sharing.report_link_default_days", 3)
        assert share(pool).status_code == 201
        assert share(pool, days=7).status_code == 400

    def test_hide_contact_must_be_yes_or_no(self, pool):
        assert share(pool, hide_contact="yes").status_code == 400

    def test_the_projects_default_decides_when_nothing_is_said(self, pool, tenant):
        Project.objects.filter(pk=tenant.project.pk).update(hide_contact_by_default=True)
        assert share(pool).json()["hide_contact"] is True
        assert share(pool, hide_contact=False).json()["hide_contact"] is False
        assert tenant.client.get(base(tenant)).json()["hide_contact_default"] is True

    def test_contacts_are_shown_by_default_until_the_project_says_otherwise(self, pool, tenant):
        assert share(pool).json()["hide_contact"] is False
        assert tenant.client.get(base(tenant)).json()["hide_contact_default"] is False

    def test_nothing_to_share_without_scored_candidates(self, tenant):
        response = share(tenant)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "nothing_to_share"

    def test_the_token_is_never_stored(self, pool):
        token = share(pool).json()["token"]
        report = SharedReport.objects.get()
        assert token not in report.token_hash and len(report.token_hash) == 64
        assert token not in str(report.entries)

    def test_tokens_are_different_each_time(self, pool):
        assert share(pool).json()["token"] != share(pool).json()["token"]

    def test_it_is_written_in_the_activity_log(self, pool):
        share(pool, days=30, hide_contact=True)
        entry = ActivityEntry.objects.get(kind="share")
        assert entry.details == {"action": "created", "days": 30, "hide_contact": True}

    def test_any_team_member_may_share_but_not_another_company(self, pool):
        person = make_company_user(pool.company, role="member")
        issued = start_session_for(
            user_id=person.pk, role="member", company_id=pool.company.pk, kind="company"
        )
        member = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert share(pool, client=member).status_code == 201
        other = Tenant(make_plan())
        assert share(pool, client=other.client).status_code == 404
        assert APIClient().post(base(pool), {}, format="json").status_code == 401


class TestPublicPage:
    def test_shows_rank_score_grade_strengths_and_risks(self, pool):
        token = share(pool).json()["token"]
        response = public(token)
        assert response.status_code == 200
        body = response.json()
        assert [e["rank"] for e in body["entries"]] == [1, 2]
        first = body["entries"][0]
        assert (first["score"], first["grade"]) == ("90.0", "A")
        assert first["strengths"] == ["Strong Python"] and first["risks"] == ["Short tenure"]
        assert first["contact"]["name"] == "Anna Example"
        assert body["entries"][1]["contact"]["phone"] == "+1 555 0100"
        assert body["title"] == pool.project.title

    def test_only_the_top_candidates_are_in_it(self, pool):
        text = public(share(pool).json()["token"]).content.decode()
        assert "Cara" not in text and "cara.pdf" not in text and "ben.pdf" not in text

    def test_hidden_contact_details_are_not_in_the_answer_or_the_database_row(self, pool):
        token = share(pool, hide_contact=True).json()["token"]
        text = public(token).content.decode()
        for secret in ("Anna", "Ben", "example.com", "555", "anna.pdf"):
            assert secret not in text
        assert "Candidate 1" in text and '"contact":' not in text
        assert SharedReport.objects.get().contacts == ""

    def test_the_contacts_are_stored_encrypted(self, pool):
        share(pool)
        with connection.cursor() as cursor:
            cursor.execute("select contacts from cvs_sharedreport")
            raw = cursor.fetchone()[0]
        assert "Anna" not in raw and "example.com" not in raw

    def test_the_report_is_a_frozen_copy(self, pool):
        token = share(pool).json()["token"]
        add(pool, "zed.pdf", 99, minutes=9, who="Zed Example")
        Candidate.objects.filter(cv_file__original_name="anna.pdf").update(stage="rejected")
        CandidateScore.objects.update(strengths=["changed"])
        body = public(token).json()
        assert [e["contact"]["name"] for e in body["entries"]] == ["Anna Example", "Ben Example"]
        assert body["entries"][0]["strengths"] == ["Strong Python"]

    def test_views_are_counted(self, pool):
        token = share(pool).json()["token"]
        for _ in range(3):
            public(token)
        assert SharedReport.objects.get().views == 3
        assert pool.client.get(base(pool)).json()["reports"][0]["views"] == 3

    def test_it_needs_no_sign_in_and_is_not_cached(self, pool):
        token = share(pool).json()["token"]
        response = public(token)
        assert response.status_code == 200
        assert response["Cache-Control"] == "private, no-store"

    def test_an_unknown_link_is_no_longer_available(self, pool):
        response = public("not-a-real-token")
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "This report is no longer available."

    def test_an_expired_link_is_no_longer_available_and_not_counted(self, pool):
        token = share(pool).json()["token"]
        SharedReport.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = public(token)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "This report is no longer available."
        assert SharedReport.objects.get().views == 0

    def test_it_stops_exactly_at_the_expiry_time(self, pool):
        token = share(pool).json()["token"]
        SharedReport.objects.update(expires_at=timezone.now() + timedelta(seconds=30))
        assert public(token).status_code == 200

    def test_all_the_ways_of_being_unavailable_look_the_same(self, pool):
        live = share(pool).json()
        revoked = share(pool).json()
        pool.client.post(f"{base(pool)}{revoked['id']}/revoke/")
        answers = {public(revoked["token"]).content, public("x" * 43).content}
        assert len(answers) == 1
        assert public(live["token"]).status_code == 200


class TestListAndRevoke:
    def test_the_list_shows_status_and_views_but_never_the_token(self, pool):
        share(pool)
        shown = pool.client.get(base(pool)).json()["reports"]
        assert len(shown) == 1 and "token" not in shown[0]
        assert shown[0]["status"] == "active"
        SharedReport.objects.update(expires_at=timezone.now() - timedelta(days=1))
        assert pool.client.get(base(pool)).json()["reports"][0]["status"] == "expired"

    def test_the_list_offers_the_expiry_choices_from_the_settings(self, pool):
        assert pool.client.get(base(pool)).json()["days"] == {"choices": [1, 7, 30], "default": 7}

    def test_revoking_stops_the_link_at_once(self, pool):
        created = share(pool).json()
        assert public(created["token"]).status_code == 200
        response = pool.client.post(f"{base(pool)}{created['id']}/revoke/")
        assert response.status_code == 200 and response.json()["status"] == "revoked"
        answer = public(created["token"])
        assert answer.status_code == 404
        assert answer.json()["error"]["message"] == "This report is no longer available."

    def test_revoking_twice_is_fine_and_logged_once(self, pool):
        created = share(pool).json()
        link = f"{base(pool)}{created['id']}/revoke/"
        first = SharedReport.objects.get().revoked_at
        pool.client.post(link)
        stamp = SharedReport.objects.get().revoked_at
        assert pool.client.post(link).status_code == 200
        assert SharedReport.objects.get().revoked_at == stamp and first is None
        assert ActivityEntry.objects.filter(details__action="revoked").count() == 1

    def test_other_companies_and_wrong_ids_are_not_found(self, pool):
        created = share(pool).json()
        other = Tenant(make_plan())
        link = f"/api/company/projects/{other.project.pk}/reports/{created['id']}/revoke/"
        assert other.client.post(link).status_code == 404
        assert pool.client.post(f"{base(pool)}nope/revoke/").status_code == 404
        assert SharedReport.objects.get().revoked_at is None

    def test_the_list_only_shows_the_projects_own_reports(self, pool):
        share(pool)
        other = Tenant(make_plan())
        assert other.client.get(base(other)).json()["reports"] == []

    def test_the_query_count_does_not_grow(self, pool):
        token = share(pool).json()["token"]
        with CaptureQueriesContext(connection) as small:
            public(token)
        for number in range(5):
            add(pool, f"x{number}.pdf", 95 + number / 10, minutes=20 + number)
        top_n(pool, 8)
        token = share(pool).json()["token"]
        with CaptureQueriesContext(connection) as large:
            public(token)
        assert len(large) == len(small)


def test_deleting_the_project_removes_its_reports(pool):
    from projects.deletion import DATA_REMOVERS

    share(pool)
    DATA_REMOVERS["SharedReport"](pool.company.pk, pool.project.pk)
    assert SharedReport.objects.count() == 0
