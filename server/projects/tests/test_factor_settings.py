import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for
from plans import subscriptions as subs
from plans.models import Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects import factor_settings
from projects.factor_settings import FACTORS
from projects.models import Project, ProjectFactorSettings

pytestmark = pytest.mark.django_db


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def company():
    company = make_company()
    now = timezone.now()
    plan = Plan.objects.create(
        name="Basic",
        status="active",
        price_usd=10,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=10000,
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


@pytest.fixture
def signed_in(company):
    return sign_in(company)


@pytest.fixture
def client(signed_in):
    return signed_in[1]


@pytest.fixture
def project(company, signed_in):
    return Project.objects.create(
        company=company,
        title="T",
        job_description="text",
        reading_model="m",
        created_by=signed_in[0],
    )


def url(project):
    return f"/api/company/projects/{project.pk}/factors/"


def body(**changes):
    factors = {name: {"enabled": False, "weight": 50} for name in FACTORS}
    return {
        "required_years": None,
        "required_education": None,
        "seniority": None,
        "factors": factors,
        **changes,
    }


def put(client, project, **changes):
    return client.put(url(project), body(**changes), format="json")


class TestDefaults:
    def test_a_new_project_has_every_factor_off_with_the_default_weight(self, client, project):
        data = client.get(url(project)).json()
        assert set(data["factors"]) == set(FACTORS)
        assert all(s == {"enabled": False, "weight": 50} for s in data["factors"].values())
        assert (data["required_years"], data["required_education"], data["seniority"]) == (
            None,
            None,
            None,
        )

    def test_the_default_weight_is_a_platform_setting(self, client, project):
        PlatformSetting.objects.create(key="factors.default_weight", value=80)
        clear_cache()
        assert client.get(url(project)).json()["factors"]["recency"]["weight"] == 80

    def test_the_seven_factors_are_the_ones_the_ticket_names(self):
        assert FACTORS == (
            "experience_years",
            "education",
            "seniority",
            "recency",
            "gaps_and_changes",
            "readability",
            "confidence",
        )


class TestSwitchingAndWeighting:
    def test_each_factor_can_be_switched_and_weighted_on_its_own(self, client, project):
        for name in FACTORS:
            factors = body()["factors"]
            factors[name] = {"enabled": True, "weight": 73}
            answer = put(client, project, factors=factors)
            assert answer.status_code == 200
            saved = client.get(url(project)).json()["factors"]
            assert saved[name] == {"enabled": True, "weight": 73}
            assert all(saved[other]["enabled"] is False for other in FACTORS if other != name)

    def test_the_ends_of_the_weight_range_are_allowed(self, client, project):
        factors = body()["factors"]
        factors["recency"]["weight"] = 0
        factors["education"]["weight"] = 100
        assert put(client, project, factors=factors).status_code == 200

    @pytest.mark.parametrize("weight", [-1, 101, 1_000])
    def test_a_weight_outside_zero_to_hundred_is_refused(self, client, project, weight):
        factors = body()["factors"]
        factors["recency"]["weight"] = weight
        answer = put(client, project, factors=factors)
        assert answer.status_code == 400 and "factors.recency" in answer.json()["error"]["fields"]
        assert not ProjectFactorSettings.objects.exists()

    def test_the_weights_do_not_have_to_add_up_to_anything(self, client, project):
        factors = {name: {"enabled": True, "weight": 100} for name in FACTORS}
        assert put(client, project, factors=factors).status_code == 200

    @pytest.mark.parametrize("weight", [1.5, "5", None, True])
    def test_a_weight_that_is_not_a_whole_number_is_refused(self, client, project, weight):
        factors = body()["factors"]
        factors["recency"]["weight"] = weight
        assert put(client, project, factors=factors).status_code == 400

    def test_a_missing_or_unknown_factor_is_refused(self, client, project):
        factors = body()["factors"]
        del factors["recency"]
        assert put(client, project, factors=factors).status_code == 400
        factors = body()["factors"]
        factors["luck"] = {"enabled": True, "weight": 5}
        assert put(client, project, factors=factors).status_code == 400

    def test_unknown_fields_and_missing_fields_are_refused(self, client, project):
        assert client.put(url(project), {**body(), "x": 1}, format="json").status_code == 400
        incomplete = body()
        del incomplete["seniority"]
        assert client.put(url(project), incomplete, format="json").status_code == 400

    def test_saving_twice_keeps_one_row(self, client, project):
        put(client, project)
        put(client, project, required_years=3)
        assert ProjectFactorSettings.objects.count() == 1


class TestWhatTheJobExpects:
    def test_the_three_job_fields_save_and_read_back(self, client, project):
        put(client, project, required_years=5, required_education="master", seniority="senior")
        data = client.get(url(project)).json()
        assert (data["required_years"], data["required_education"], data["seniority"]) == (
            5,
            "master",
            "senior",
        )

    def test_they_can_be_cleared(self, client, project):
        put(client, project, required_years=5)
        put(client, project)
        assert client.get(url(project)).json()["required_years"] is None

    @pytest.mark.parametrize("years", [-1, 61, 1000])
    def test_years_outside_the_range_are_refused(self, client, project, years):
        answer = put(client, project, required_years=years)
        assert answer.status_code == 400 and "required_years" in answer.json()["error"]["fields"]

    def test_the_largest_years_is_a_platform_setting(self, client, project):
        PlatformSetting.objects.create(key="factors.max_required_years", value=10)
        clear_cache()
        assert put(client, project, required_years=11).status_code == 400
        assert put(client, project, required_years=10).status_code == 200

    @pytest.mark.parametrize("level", ["school", "BACHELOR", ""])
    def test_an_unknown_education_level_is_refused(self, client, project, level):
        assert put(client, project, required_education=level).status_code == 400

    @pytest.mark.parametrize("level", ["boss", "Senior", ""])
    def test_an_unknown_seniority_is_refused(self, client, project, level):
        assert put(client, project, seniority=level).status_code == 400

    def test_zero_years_is_allowed(self, client, project):
        assert put(client, project, required_years=0).status_code == 200


class TestRecalculation:
    @pytest.fixture
    def calls(self, monkeypatch):
        made = []
        monkeypatch.setattr(
            factor_settings, "recalculate_scores", lambda project: made.append(project.pk) or 0
        )
        return made

    def test_a_change_recombines_scores_without_the_ai(self, client, project, calls, monkeypatch):
        from ai import client as ai_client

        monkeypatch.setattr(ai_client, "_send", lambda **c: pytest.fail("the AI was called"))
        factors = body()["factors"]
        factors["recency"]["enabled"] = True
        put(client, project, factors=factors)
        assert calls == [project.pk]

    def test_saving_the_same_values_recalculates_nothing(self, client, project, calls):
        put(client, project, required_years=4)
        put(client, project, required_years=4)
        assert calls == [project.pk]

    def test_a_refused_save_recalculates_nothing(self, client, project, calls):
        put(client, project, required_years=1000)
        assert calls == []

    def test_changing_a_job_expectation_refreshes_the_stored_factor_values(
        self, client, project, monkeypatch
    ):
        refreshed = []
        from cvs import extra_factors

        monkeypatch.setattr(
            extra_factors, "refresh_project_factors", lambda p: refreshed.append(p.pk)
        )
        put(client, project, required_years=4)
        put(client, project, required_years=4)
        factors = body(required_years=4)["factors"]
        factors["recency"]["weight"] = 10
        put(client, project, required_years=4, factors=factors)
        assert refreshed == [project.pk]


class TestAccess:
    def test_an_archived_project_can_be_read_but_not_changed(self, client, project):
        put(client, project)
        Project.objects.filter(pk=project.pk).update(status="archived")
        assert client.get(url(project)).status_code == 200
        assert put(client, project, required_years=3).status_code == 409

    def test_nobody_signed_in_is_refused(self, project):
        assert APIClient().get(url(project)).status_code == 401
        assert APIClient().put(url(project), body(), format="json").status_code == 401

    def test_a_member_may_save(self, company, project):
        _, member = sign_in(company, "member")
        assert put(member, project).status_code == 200


class TestAnotherCompany:
    def test_another_companys_settings_cannot_be_read_or_changed(self, client):
        stranger = make_company()
        theirs = Project.objects.create(
            company=stranger,
            title="T",
            job_description="t",
            reading_model="m",
            created_by=make_company_user(stranger),
        )
        assert client.get(url(theirs)).status_code == 404
        assert put(client, theirs, required_years=3).status_code == 404
        assert not ProjectFactorSettings.objects.exists()

    def test_the_settings_belong_to_the_projects_company(self, company, client, project):
        put(client, project, required_years=2)
        assert ProjectFactorSettings.objects.get(project=project).company_id == company.pk
