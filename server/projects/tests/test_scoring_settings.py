import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for
from plans import subscriptions as subs
from plans.models import LimitOverride, Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects import scoring_settings
from projects.models import Project, ProjectScoringSettings

pytestmark = pytest.mark.django_db

DEFAULTS = {
    "must_weight_percent": 70,
    "nice_weight_percent": 30,
    "recommendation_threshold": 75,
    "top_n": 10,
}


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def make_plan(max_top_n=20, name="Basic", price=10):
    return Plan.objects.create(
        name=name,
        status="active",
        price_usd=price,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=max_top_n,
        monthly_ai_token_cap=10000,
    )


@pytest.fixture
def company():
    company = make_company()
    now = timezone.now()
    subs.activate(
        company.pk, make_plan(), period_start=now, period_end=now + timezone.timedelta(days=30)
    )
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
        title="Backend engineer",
        job_description="text",
        reading_model="m",
        prompt_version="p",
        created_by=signed_in[0],
    )


def url(project):
    return f"/api/company/projects/{project.pk}/scoring/"


def body(**changes):
    return {**DEFAULTS, **changes}


def put(client, project, **changes):
    return client.put(url(project), body(**changes), format="json")


class TestDefaults:
    def test_a_new_project_shows_the_defaults_and_the_plan_cap(self, client, project):
        shown = client.get(url(project)).json()
        assert shown == {**DEFAULTS, "top_n_cap": 20}

    def test_defaults_follow_the_platform_scoring_settings(self, client, project):
        PlatformSetting.objects.create(key="scoring.top_n", value=5)
        PlatformSetting.objects.create(key="scoring.must_have_weight_percent", value=60)
        PlatformSetting.objects.create(key="scoring.nice_to_have_weight_percent", value=40)
        clear_cache()
        shown = client.get(url(project)).json()
        assert (shown["top_n"], shown["must_weight_percent"], shown["nice_weight_percent"]) == (
            5,
            60,
            40,
        )

    def test_the_default_top_n_is_held_at_the_plan_cap(self, company, client, project):
        Plan.objects.update(max_top_n=4)
        assert client.get(url(project)).json()["top_n"] == 4

    def test_once_saved_a_project_no_longer_follows_the_defaults(self, client, project):
        put(client, project, top_n=7)
        PlatformSetting.objects.create(key="scoring.top_n", value=3)
        clear_cache()
        assert client.get(url(project)).json()["top_n"] == 7


class TestSaving:
    def test_saves_and_reads_back(self, client, project):
        response = put(
            client,
            project,
            must_weight_percent=60,
            nice_weight_percent=40,
            recommendation_threshold=80,
            top_n=5,
        )
        assert response.status_code == 200
        expected = {
            "must_weight_percent": 60,
            "nice_weight_percent": 40,
            "recommendation_threshold": 80,
            "top_n": 5,
            "top_n_cap": 20,
        }
        assert {k: v for k, v in response.json().items() if k != "recalculated"} == expected
        assert client.get(url(project)).json() == expected

    def test_saving_twice_keeps_one_row(self, client, project):
        put(client, project, top_n=5)
        put(client, project, top_n=6)
        assert ProjectScoringSettings.objects.filter(project=project).count() == 1

    def test_the_ends_of_the_ranges_are_allowed(self, client, project):
        assert (
            put(client, project, must_weight_percent=100, nice_weight_percent=0).status_code == 200
        )
        assert (
            put(client, project, must_weight_percent=0, nice_weight_percent=100).status_code == 200
        )
        assert put(client, project, recommendation_threshold=0).status_code == 200
        assert put(client, project, recommendation_threshold=100).status_code == 200
        assert put(client, project, top_n=1).status_code == 200

    def test_a_member_may_save(self, company, project):
        _, member = sign_in(company, role="member")
        assert put(member, project).status_code == 200


class TestImpossibleCombinations:
    def fields(self, response):
        return response.json()["error"]["fields"]

    def test_weights_must_total_100(self, client, project):
        response = put(client, project, must_weight_percent=70, nice_weight_percent=40)
        assert response.status_code == 400
        assert "nice_weight_percent" in self.fields(response)
        assert "add up to 100" in self.fields(response)["nice_weight_percent"]

    @pytest.mark.parametrize("must,nice", [(-10, 110), (110, -10), (101, -1)])
    def test_weights_outside_zero_to_hundred_are_refused(self, client, project, must, nice):
        response = put(client, project, must_weight_percent=must, nice_weight_percent=nice)
        assert response.status_code == 400

    @pytest.mark.parametrize("threshold", [-1, 101])
    def test_threshold_must_be_a_percent(self, client, project, threshold):
        response = put(client, project, recommendation_threshold=threshold)
        assert "recommendation_threshold" in self.fields(response)

    def test_top_n_must_be_at_least_one(self, client, project):
        assert "top_n" in self.fields(put(client, project, top_n=0))

    @pytest.mark.parametrize("value", ["x", 1.5, None])
    def test_values_must_be_whole_numbers(self, client, project, value):
        assert put(client, project, top_n=value).status_code == 400

    def test_every_value_is_required(self, client, project):
        assert client.put(url(project), {"top_n": 5}, format="json").status_code == 400

    def test_unknown_fields_are_refused(self, client, project):
        assert put(client, project, extra_factors=[1]).status_code == 400

    def test_nothing_is_saved_when_refused(self, client, project):
        put(client, project, nice_weight_percent=99)
        assert not ProjectScoringSettings.objects.exists()

    def test_the_database_itself_refuses_weights_that_do_not_total_100(self, company, project):
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectScoringSettings.objects.create(
                company=company,
                project=project,
                must_weight_percent=60,
                nice_weight_percent=60,
                recommendation_threshold=75,
                top_n=5,
            )


class TestPlanCap:
    def test_top_n_at_the_cap_is_allowed(self, client, project):
        assert put(client, project, top_n=20).status_code == 200

    def test_top_n_above_the_cap_shows_the_upgrade_prompt(self, client, project):
        make_plan(max_top_n=50, name="Bigger", price=99)
        response = put(client, project, top_n=21)
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "top_n_limit_exceeded"
        assert error["details"] == {"limit": 20, "prompt": "upgrade"}
        assert not ProjectScoringSettings.objects.exists()

    def test_an_admin_override_raises_the_cap(self, company, client, project):
        LimitOverride.objects.create(company=company, name="max_top_n", value=40)
        assert put(client, project, top_n=40).status_code == 200
        assert client.get(url(project)).json()["top_n_cap"] == 40

    def test_a_lowered_plan_holds_a_saved_top_n_at_the_new_cap(self, client, project):
        put(client, project, top_n=15)
        Plan.objects.update(max_top_n=8)
        assert client.get(url(project)).json()["top_n"] == 8

    def test_an_ended_subscription_shows_the_renewal_prompt(self, company, client, project):
        subs.expire(company.pk)
        response = put(client, project)
        assert response.status_code == 409
        assert response.json()["error"]["details"]["prompt"] == "renewal"


class TestRecalculation:
    @pytest.fixture
    def calls(self, monkeypatch):
        seen = []

        def fake(project):
            seen.append(project.pk)
            return 4

        monkeypatch.setattr(scoring_settings, "recalculate_scores", fake)
        return seen

    def test_a_change_recalculates_without_the_ai(self, client, project, calls):
        response = put(client, project, top_n=5)
        assert calls == [project.pk]
        assert response.json()["recalculated"] == 4

    def test_saving_the_same_values_recalculates_nothing(self, client, project, calls):
        put(client, project, top_n=5)
        calls.clear()
        assert put(client, project, top_n=5).json()["recalculated"] == 0
        assert calls == []

    def test_a_refused_save_recalculates_nothing(self, client, project, calls):
        put(client, project, nice_weight_percent=99)
        assert calls == []

    def test_nothing_to_recalculate_yet_reports_zero(self, client, project):
        assert put(client, project, top_n=5).json()["recalculated"] == 0

    def test_the_ai_is_never_called(self, client, project, monkeypatch):
        from ai import client as ai_client

        def forbidden(**_):
            raise AssertionError("The AI must not be called to recalculate.")

        monkeypatch.setattr(ai_client, "_send", forbidden)
        assert put(client, project, top_n=5).status_code == 200


class TestAccess:
    def test_an_archived_project_cannot_be_changed_but_can_be_read(self, client, project):
        Project.objects.filter(pk=project.pk).update(status="archived")
        assert client.get(url(project)).status_code == 200
        response = put(client, project, top_n=5)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_archived"

    def test_nobody_signed_in_is_refused(self, project):
        assert APIClient().get(url(project)).status_code == 401


class TestAnotherCompany:
    def test_another_companys_settings_cannot_be_read_or_changed(self, client):
        stranger = make_company()
        theirs = Project.objects.create(
            company=stranger,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=make_company_user(stranger),
        )
        assert client.get(url(theirs)).status_code == 404
        assert put(client, theirs, top_n=3).status_code == 404
        assert not ProjectScoringSettings.objects.exists()

    def test_the_settings_belong_to_the_projects_company(self, company, client, project):
        put(client, project, top_n=5)
        assert ProjectScoringSettings.objects.get(project=project).company_id == company.pk

    def test_one_projects_settings_do_not_touch_another(self, company, signed_in, client, project):
        other = Project.objects.create(
            company=company,
            title="Other",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=signed_in[0],
        )
        put(client, project, top_n=3)
        assert client.get(url(other)).json()["top_n"] == 10


def test_defaults_come_from_one_function():
    assert scoring_settings.scoring_defaults() == {
        **DEFAULTS,
    }
