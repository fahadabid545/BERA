import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import ActivityEntry
from core.tests.factories import make_company, make_company_user, start_session_for
from plans import subscriptions as subs
from plans.models import Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects import factor_settings, scoring_settings
from projects.factor_settings import FACTORS
from projects.models import (
    CompanyScoringDefaults,
    Project,
    ProjectFactorSettings,
    ProjectScoringSettings,
)

pytestmark = pytest.mark.django_db

URL = "/api/company/scoring-defaults/"
PROJECTS = "/api/company/projects/"
PLATFORM = {
    "must_weight_percent": 70,
    "nice_weight_percent": 30,
    "recommendation_threshold": 75,
    "top_n": 10,
    "cap_on_missing_must_have": False,
}


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def make_company_with_plan(max_top_n=20):
    company = make_company()
    plan = Plan.objects.create(
        name=f"Basic {company.pk}",
        status="active",
        price_usd=10,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=20,
        max_team_accounts=3,
        max_top_n=max_top_n,
        monthly_ai_token_cap=10000,
    )
    now = timezone.now()
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


@pytest.fixture
def company():
    return make_company_with_plan()


@pytest.fixture
def owner(company):
    return sign_in(company)


def factors(**switched):
    return {
        name: {"enabled": name in switched, "weight": switched.get(name, 50)} for name in FACTORS
    }


def body(**changes):
    return {**PLATFORM, "factors": factors(), **changes}


def new_project(client, title="New role"):
    response = client.post(
        PROJECTS,
        {"title": title, "job_description": "x" * 400, "acknowledge_warnings": True},
        format="json",
    )
    assert response.status_code == 201
    return Project.objects.get(pk=response.json()["id"])


def old_project(company, person, title="Old role"):
    return Project.objects.create(
        company=company,
        title=title,
        job_description="text",
        reading_model="m",
        created_by=person,
    )


class TestReading:
    def test_a_company_that_saved_none_sees_the_platform_values(self, owner):
        shown = owner[1].get(URL).json()
        assert {k: shown[k] for k in PLATFORM} == PLATFORM
        assert shown["top_n_cap"] == 20
        assert set(shown["factors"]) == set(FACTORS)
        assert all(not setting["enabled"] for setting in shown["factors"].values())

    def test_the_platform_values_follow_the_platform_settings(self, owner):
        PlatformSetting.objects.create(key="scoring.top_n", value=5)
        clear_cache()
        assert owner[1].get(URL).json()["top_n"] == 5

    def test_the_saved_values_are_read_back(self, owner):
        chosen = body(
            must_weight_percent=60,
            nice_weight_percent=40,
            recommendation_threshold=80,
            top_n=4,
            cap_on_missing_must_have=True,
            factors=factors(recency=30, readability=10),
        )
        assert owner[1].put(URL, chosen, format="json").status_code == 200
        shown = owner[1].get(URL).json()
        assert shown == {**chosen, "top_n_cap": 20}

    def test_a_top_n_above_a_lowered_plan_cap_is_held_at_the_cap(self, company, owner):
        owner[1].put(URL, body(top_n=15), format="json")
        Plan.objects.update(max_top_n=6)
        assert owner[1].get(URL).json()["top_n"] == 6


class TestWhoMaySet:
    def test_a_member_may_neither_read_nor_save(self, company):
        _, member = sign_in(company, role="member")
        assert member.get(URL).status_code == 403
        assert member.put(URL, body(), format="json").status_code == 403
        assert not CompanyScoringDefaults.objects.exists()

    def test_nobody_signed_out_may_read_or_save(self):
        client = APIClient()
        assert client.get(URL).status_code == 401
        assert client.put(URL, body(), format="json").status_code == 401


class TestChecks:
    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"must_weight_percent": 60, "nice_weight_percent": 60}, "nice_weight_percent"),
            ({"must_weight_percent": 120, "nice_weight_percent": -20}, "must_weight_percent"),
            ({"recommendation_threshold": 101}, "recommendation_threshold"),
            ({"top_n": 0}, "top_n"),
        ],
    )
    def test_impossible_numbers_are_refused_with_the_field(self, owner, changes, field):
        response = owner[1].put(URL, body(**changes), format="json")
        assert response.status_code == 400
        assert field in response.json()["error"]["fields"]
        assert not CompanyScoringDefaults.objects.exists()

    def test_a_top_n_above_the_plan_cap_is_refused(self, owner):
        response = owner[1].put(URL, body(top_n=21), format="json")
        assert response.status_code == 409
        assert not CompanyScoringDefaults.objects.exists()

    def test_a_factor_weight_outside_zero_to_hundred_is_refused(self, owner):
        bad = factors()
        bad["recency"] = {"enabled": True, "weight": 101}
        response = owner[1].put(URL, body(factors=bad), format="json")
        assert response.status_code == 400
        assert "factors.recency" in response.json()["error"]["fields"]

    def test_every_factor_must_be_given(self, owner):
        partial = factors()
        del partial["recency"]
        response = owner[1].put(URL, body(factors=partial), format="json")
        assert response.status_code == 400
        assert "factors" in response.json()["error"]["fields"]

    def test_a_value_that_is_not_a_setting_is_refused(self, owner):
        assert owner[1].put(URL, {**body(), "company_id": "x"}, format="json").status_code == 400

    def test_saving_is_logged_without_the_values(self, company, owner):
        owner[1].put(URL, body(top_n=3), format="json")
        entry = ActivityEntry.objects.get(company=company, kind="setting_changed")
        assert entry.details == {"setting": "scoring_defaults"}


class TestNewProjectsStartFromTheDefaults:
    def test_a_new_project_gets_the_scoring_numbers_and_the_factors(self, company, owner):
        chosen = body(
            must_weight_percent=55,
            nice_weight_percent=45,
            recommendation_threshold=82,
            top_n=3,
            cap_on_missing_must_have=True,
            factors=factors(recency=30, confidence=20),
        )
        owner[1].put(URL, chosen, format="json")
        project = new_project(owner[1])
        scoring = scoring_settings.describe(project)
        assert {k: scoring[k] for k in PLATFORM} == {k: chosen[k] for k in PLATFORM}
        shown = factor_settings.effective_factors(project)["factors"]
        assert shown["recency"] == {"enabled": True, "weight": 30}
        assert shown["confidence"] == {"enabled": True, "weight": 20}
        assert shown["education"]["enabled"] is False

    def test_the_project_keeps_its_own_copy_in_its_own_rows(self, owner):
        owner[1].put(URL, body(top_n=3), format="json")
        project = new_project(owner[1])
        assert ProjectScoringSettings.objects.get(project=project).top_n == 3
        assert ProjectFactorSettings.objects.filter(project=project).exists()

    def test_a_company_with_no_defaults_starts_projects_from_the_platform(self, owner):
        project = new_project(owner[1])
        assert not ProjectScoringSettings.objects.filter(project=project).exists()
        assert not ProjectFactorSettings.objects.filter(project=project).exists()
        assert scoring_settings.describe(project)["top_n"] == 10

    def test_the_job_expectations_start_empty(self, owner):
        owner[1].put(URL, body(factors=factors(experience_years=40)), format="json")
        shown = factor_settings.effective_factors(new_project(owner[1]))
        assert (shown["required_years"], shown["required_education"], shown["seniority"]) == (
            None,
            None,
            None,
        )


class TestExistingProjectsAreNeverChanged:
    def test_a_project_with_its_own_settings_keeps_them(self, company, owner):
        project = new_project(owner[1])
        own = {**PLATFORM, "top_n": 7}
        owner[1].put(f"{PROJECTS}{project.pk}/scoring/", own, format="json")
        owner[1].put(URL, body(top_n=2, recommendation_threshold=90), format="json")
        shown = scoring_settings.describe(project)
        assert (shown["top_n"], shown["recommendation_threshold"]) == (7, 75)

    def test_a_project_that_follows_the_platform_does_not_pick_up_the_defaults(
        self, company, owner
    ):
        project = old_project(company, owner[0])
        owner[1].put(
            URL, body(top_n=2, factors=factors(recency=90), cap_on_missing_must_have=True), "json"
        )
        shown = scoring_settings.describe(project)
        assert (shown["top_n"], shown["cap_on_missing_must_have"]) == (10, False)
        assert factor_settings.effective_factors(project)["factors"]["recency"]["enabled"] is False

    def test_changing_the_defaults_again_leaves_a_project_made_from_the_first(self, owner):
        owner[1].put(URL, body(top_n=3, factors=factors(recency=30)), format="json")
        earlier = new_project(owner[1], "Earlier")
        owner[1].put(URL, body(top_n=9, factors=factors(readability=40)), format="json")
        later = new_project(owner[1], "Later")
        assert scoring_settings.describe(earlier)["top_n"] == 3
        assert factor_settings.effective_factors(earlier)["factors"]["recency"]["enabled"]
        assert not factor_settings.effective_factors(earlier)["factors"]["readability"]["enabled"]
        assert scoring_settings.describe(later)["top_n"] == 9
        assert factor_settings.effective_factors(later)["factors"]["readability"]["enabled"]

    def test_saving_the_defaults_recalculates_nothing(self, company, owner, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "projects.scoring_settings.recalculate_scores", lambda project: calls.append(project)
        )
        monkeypatch.setattr(
            "projects.factor_settings.recalculate_scores", lambda project: calls.append(project)
        )
        old_project(company, owner[0])
        owner[1].put(URL, body(top_n=2), format="json")
        assert calls == []


class TestAnotherCompany:
    def test_defaults_are_kept_apart_per_company(self, company, owner):
        other = make_company_with_plan()
        _, theirs = sign_in(other)
        owner[1].put(URL, body(top_n=2), format="json")
        assert theirs.get(URL).json()["top_n"] == 10
        assert CompanyScoringDefaults.objects.get().company_id == company.pk

    def test_a_project_of_another_company_is_made_from_its_own_defaults(self, owner):
        other = make_company_with_plan()
        _, theirs = sign_in(other)
        owner[1].put(URL, body(top_n=2), format="json")
        project = new_project(theirs)
        assert not ProjectScoringSettings.objects.filter(project=project).exists()
        assert scoring_settings.describe(project)["top_n"] == 10

    def test_saving_twice_keeps_one_row_for_the_company(self, company, owner):
        owner[1].put(URL, body(top_n=2), format="json")
        owner[1].put(URL, body(top_n=4), format="json")
        assert CompanyScoringDefaults.objects.filter(company=company).count() == 1
