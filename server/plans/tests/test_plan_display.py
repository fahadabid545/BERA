import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from companies.tests.test_invites import client_of, team
from core.tests.factories import make_admin_user, make_company_user
from plans import limits
from plans import subscriptions as subs
from plans.models import LimitOverride, Plan
from plans.summary import warning_level
from platform_settings.service import get_setting
from signin import service as signin
from usage import service as usage

pytestmark = pytest.mark.django_db
URL = "/api/company/usage/"
DAY = timedelta(days=1)


@pytest.fixture
def plan():
    return Plan.objects.create(
        name="Fake Plan",
        status="active",
        price_usd=Decimal("10"),
        cvs_per_month=10,
        cvs_per_project=5,
        max_projects=3,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=1000,
    )


@pytest.fixture
def owned(plan):
    company, owner = team()
    now = timezone.now()
    subs.activate(company.pk, plan, period_start=now, period_end=now + 30 * DAY)
    return company, client_of(owner)


def summary(client):
    response = client.get(URL)
    assert response.status_code == 200, response.content
    return response.json()


def score(company, count):
    for _ in range(count):
        cv = uuid.uuid4()
        usage.accept_cv(company.pk, cv)
        usage.mark_scored(company.pk, cv)


class TestTheNumbers:
    def test_a_new_subscription_shows_zeros_and_the_plan(self, owned):
        company, client = owned
        data = summary(client)
        assert data["plan_name"] == "Fake Plan"
        assert data["state"] == "active"
        assert data["cvs"] == {"used": 0, "limit": 10, "left": 10, "warning": None}
        assert data["tokens"] == {"used": 0, "limit": 1000, "left": 1000, "warning": None}
        assert data["projects"] == {"used": 0, "limit": 3}
        assert data["estimated_cost"] == "0.000000"

    def test_the_period_dates_are_the_current_usage_period(self, owned):
        company, client = owned
        data = summary(client)
        start, end = usage.window_for(company.pk, timezone.now())
        assert (data["period_start"], data["period_end"]) == (
            start.isoformat().replace("+00:00", "Z"),
            end.isoformat().replace("+00:00", "Z"),
        )

    def test_figures_match_the_counters(self, owned):
        company, client = owned
        score(company, 3)
        usage.accept_cv(company.pk, uuid.uuid4())  # waiting counts as used too
        cv = uuid.uuid4()
        usage.accept_cv(company.pk, cv)
        usage.add_tokens(company.pk, 300, 120, "0.012345", cv_id=cv)
        data = summary(client)
        assert data["cvs"]["used"] == 5 and data["cvs"]["left"] == 5
        assert (data["tokens"]["used"], data["tokens"]["left"]) == (420, 580)
        assert data["estimated_cost"] == "0.012345"

    def test_figures_match_what_the_limit_checks_enforce(self, owned):
        company, client = owned
        score(company, 4)
        usage.add_tokens(company.pk, 700, 100, "0.1")
        data = summary(client)
        month = limits.check_cvs_this_month(company.pk)
        assert (data["cvs"]["used"], data["cvs"]["left"], data["cvs"]["limit"]) == (
            month.used,
            month.room,
            month.limit,
        )
        ai = limits.check_ai_allowed(company.pk)
        assert (data["tokens"]["used"], data["tokens"]["limit"]) == (ai.used, ai.limit)

    def test_a_failed_cv_gives_its_cv_back_in_the_display(self, owned):
        company, client = owned
        cv = uuid.uuid4()
        usage.accept_cv(company.pk, cv)
        assert summary(client)["cvs"]["used"] == 1
        usage.mark_failed(company.pk, cv)
        assert summary(client)["cvs"]["used"] == 0

    def test_an_admin_limit_change_shows_at_once(self, owned):
        company, client = owned
        LimitOverride.objects.create(company=company, name="cvs_per_month", value=20)
        assert summary(client)["cvs"]["limit"] == 20

    def test_a_new_period_starts_from_zero(self, owned):
        company, client = owned
        old = uuid.uuid4()
        usage.accept_cv(company.pk, old, now=timezone.now() - 40 * DAY)
        usage.mark_scored(company.pk, old)
        assert summary(client)["cvs"]["used"] == 0

    def test_a_company_with_no_plan_shows_no_plan_and_no_warnings(self):
        company, owner = team()
        data = summary(client_of(owner))
        assert (data["plan_name"], data["state"]) == (None, "no_plan")
        assert data["cvs"] == {"used": 0, "limit": 0, "left": 0, "warning": None}

    def test_past_due_shows_when_the_grace_period_ends(self, owned):
        company, client = owned
        subs.mark_past_due(company.pk)
        data = summary(client)
        assert data["state"] == "past_due" and data["grace_ends_at"] is not None

    def test_another_companys_usage_is_never_shown(self, owned):
        company, client = owned
        other, _ = team()
        score(other, 6)
        assert summary(client)["cvs"]["used"] == 0

    def test_it_says_how_often_to_refresh(self, owned):
        _, client = owned
        assert summary(client)["refresh_seconds"] == get_setting("live_updates.max_delay_seconds")


class TestWarnings:
    @pytest.mark.parametrize(
        ("used", "expected"),
        [(0, None), (79, None), (80, 80), (99, 80), (100, 100), (150, 100)],
    )
    def test_the_thresholds(self, used, expected):
        assert warning_level(used, 100) == expected

    def test_a_limit_of_zero_has_no_warning(self):
        assert warning_level(5, 0) is None

    def test_cv_warnings_appear_at_80_and_100_percent(self, owned):
        company, client = owned
        score(company, 7)
        assert summary(client)["cvs"]["warning"] is None
        score(company, 1)
        assert summary(client)["cvs"]["warning"] == 80
        score(company, 1)
        assert summary(client)["cvs"]["warning"] == 80
        score(company, 1)
        assert summary(client)["cvs"]["warning"] == 100

    def test_token_warnings_appear_at_80_and_100_percent(self, owned):
        company, client = owned
        usage.add_tokens(company.pk, 700, 99, "0")
        assert summary(client)["tokens"]["warning"] is None
        usage.add_tokens(company.pk, 1, 0, "0")
        assert summary(client)["tokens"]["warning"] == 80
        usage.add_tokens(company.pk, 100, 100, "0")
        assert summary(client)["tokens"]["warning"] == 100

    def test_cv_and_token_warnings_are_separate(self, owned):
        company, client = owned
        score(company, 10)
        data = summary(client)
        assert (data["cvs"]["warning"], data["tokens"]["warning"]) == (100, None)

    def test_the_thresholds_follow_the_platform_setting(self, owned, monkeypatch):
        company, client = owned
        monkeypatch.setattr(
            "plans.summary.get_setting",
            lambda name: [50] if name == "usage.warning_percents" else 3,
        )
        score(company, 5)
        assert summary(client)["cvs"]["warning"] == 50


class TestWhoMayRead:
    def test_a_member_is_refused(self, owned):
        company, _ = owned
        member = make_company_user(company, role="member")
        assert client_of(member).get(URL).status_code == 403

    def test_a_visitor_is_refused(self, owned):
        assert APIClient().get(URL).status_code == 401

    def test_an_admin_session_is_refused(self, owned):
        admin = make_admin_user(role="super")
        issued = signin.start_session(user_id=admin.pk, role="super", company_id=None, kind="admin")
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.get(URL).status_code == 401

    def test_it_is_read_only(self, owned):
        _, client = owned
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(URL, {}, format="json").status_code == 405
