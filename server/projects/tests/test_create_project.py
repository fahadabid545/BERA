import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for
from plans import subscriptions as subs
from plans.models import LimitOverride, Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project

pytestmark = pytest.mark.django_db
URL = "/api/company/projects/"
LONG_TEXT = "Looking for a careful engineer. " * 20  # well over 300 characters


def make_plan(max_projects=5):
    return Plan.objects.create(
        name="Basic",
        status="active",
        price_usd=10,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=max_projects,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=100000,
    )


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def subscribe(company, plan):
    now = timezone.now()
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))


@pytest.fixture
def company():
    company = make_company()
    subscribe(company, make_plan())
    return company


def body(**changes):
    return {"title": "Backend engineer", "job_description": LONG_TEXT, **changes}


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


class TestCreating:
    def test_creates_a_project_in_the_users_company(self, company):
        person, client = sign_in(company)
        response = client.post(URL, body(), format="json")
        assert response.status_code == 201
        project = Project.objects.get(pk=response.json()["id"])
        assert project.company_id == company.pk
        assert project.created_by_id == person.pk
        assert project.title == "Backend engineer"
        assert project.job_description == LONG_TEXT.strip()

    def test_a_member_may_create_too(self, company):
        _, client = sign_in(company, role="member")
        assert client.post(URL, body(), format="json").status_code == 201

    def test_the_company_cannot_be_chosen_in_the_request(self, company):
        other = make_company()
        _, client = sign_in(company)
        response = client.post(URL, body(company=str(other.pk)), format="json")
        assert response.status_code == 400
        assert not Project.objects.exists()

    def test_nobody_signed_in_is_refused(self):
        assert APIClient().post(URL, body(), format="json").status_code == 401


class TestPinnedSetup:
    def test_the_current_defaults_are_pinned(self, company):
        _, client = sign_in(company)
        project = Project.objects.get(pk=client.post(URL, body(), format="json").json()["id"])
        assert project.reading_model == "standin-reading-model"
        assert (project.reading_prompt_version, project.scoring_prompt_version) == (1, 1)

    def test_a_later_default_does_not_change_an_existing_project(self, company):
        _, client = sign_in(company)
        first = client.post(URL, body(title="First"), format="json").json()["id"]
        set_setting("ai.reading_model", "newer-model")
        set_setting("ai.reading_prompt_version", 2)
        set_setting("ai.scoring_prompt_version", 3)
        second = client.post(URL, body(title="Second"), format="json").json()["id"]
        assert Project.objects.get(pk=first).reading_model == "standin-reading-model"
        old = Project.objects.get(pk=first)
        assert (old.reading_prompt_version, old.scoring_prompt_version) == (1, 1)
        assert Project.objects.get(pk=second).reading_model == "newer-model"
        new = Project.objects.get(pk=second)
        assert (new.reading_prompt_version, new.scoring_prompt_version) == (2, 3)


class TestFields:
    @pytest.mark.parametrize("field", ["title", "job_description"])
    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_both_fields_are_required(self, company, field, value):
        _, client = sign_in(company)
        response = client.post(URL, body(**{field: value}), format="json")
        assert response.status_code == 400
        assert field in response.json()["error"]["fields"]

    def test_title_is_limited_to_120_characters(self, company):
        _, client = sign_in(company)
        assert client.post(URL, body(title="a" * 120), format="json").status_code == 201
        response = client.post(URL, body(title="a" * 121), format="json")
        assert "title" in response.json()["error"]["fields"]

    def test_description_is_limited_to_15000_characters(self, company):
        _, client = sign_in(company)
        assert client.post(URL, body(job_description="a" * 15000), format="json").status_code == 201
        response = client.post(URL, body(job_description="a" * 15001), format="json")
        assert "job_description" in response.json()["error"]["fields"]

    def test_the_limits_come_from_platform_settings(self, company):
        set_setting("projects.title_max_length", 20)
        _, client = sign_in(company)
        assert client.post(URL, body(title="a" * 21), format="json").status_code == 400

    def test_line_breaks_in_the_description_are_kept(self, company):
        _, client = sign_in(company)
        text = "Line one\nLine two " + LONG_TEXT
        project = Project.objects.get(
            pk=client.post(URL, body(job_description=text), format="json").json()["id"]
        )
        assert "\n" in project.job_description

    def test_a_line_break_in_the_title_is_refused(self, company):
        _, client = sign_in(company)
        assert client.post(URL, body(title="Two\nlines"), format="json").status_code == 400


class TestWarnings:
    def warning_codes(self, response):
        return [item["code"] for item in response.json()["error"]["details"]["warnings"]]

    def test_a_short_description_warns_and_creates_nothing_yet(self, company):
        _, client = sign_in(company)
        response = client.post(URL, body(job_description="a" * 299), format="json")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_warnings"
        assert self.warning_codes(response) == ["short_description"]
        assert not Project.objects.exists()

    def test_exactly_300_characters_does_not_warn(self, company):
        _, client = sign_in(company)
        assert client.post(URL, body(job_description="a" * 300), format="json").status_code == 201

    def test_a_short_description_is_created_once_confirmed(self, company):
        _, client = sign_in(company)
        response = client.post(
            URL, body(job_description="short", acknowledge_warnings=True), format="json"
        )
        assert response.status_code == 201

    def test_a_duplicate_title_warns_in_any_case_and_is_allowed_once_confirmed(self, company):
        _, client = sign_in(company)
        client.post(URL, body(), format="json")
        response = client.post(URL, body(title="BACKEND ENGINEER"), format="json")
        assert response.status_code == 409
        assert self.warning_codes(response) == ["duplicate_title"]
        confirmed = client.post(
            URL, body(title="BACKEND ENGINEER", acknowledge_warnings=True), format="json"
        )
        assert confirmed.status_code == 201
        assert Project.objects.filter(company=company).count() == 2

    def test_both_warnings_arrive_together(self, company):
        _, client = sign_in(company)
        client.post(URL, body(), format="json")
        response = client.post(URL, body(job_description="short"), format="json")
        assert self.warning_codes(response) == ["short_description", "duplicate_title"]

    def test_another_companys_title_is_not_a_duplicate(self, company):
        other = make_company()
        subscribe(other, Plan.objects.first())
        _, other_client = sign_in(other)
        other_client.post(URL, body(), format="json")
        _, client = sign_in(company)
        assert client.post(URL, body(), format="json").status_code == 201

    def test_the_short_length_comes_from_platform_settings(self, company):
        set_setting("projects.short_description_length", 50)
        _, client = sign_in(company)
        assert client.post(URL, body(job_description="a" * 60), format="json").status_code == 201

    def test_acknowledging_must_be_a_real_answer(self, company):
        _, client = sign_in(company)
        response = client.post(URL, body(acknowledge_warnings="maybe"), format="json")
        assert response.status_code == 400


class TestProjectLimit:
    def test_the_limit_shows_the_upgrade_prompt(self, company):
        Plan.objects.all().update(max_projects=1)
        make_plan_higher = Plan.objects.create(
            name="Bigger",
            status="active",
            price_usd=99,
            cvs_per_month=1,
            cvs_per_project=1,
            max_projects=9,
            max_team_accounts=1,
            max_top_n=1,
            monthly_ai_token_cap=1,
        )
        assert make_plan_higher
        _, client = sign_in(company)
        assert client.post(URL, body(), format="json").status_code == 201
        response = client.post(URL, body(title="Second"), format="json")
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "project_limit_reached"
        assert error["details"] == {"limit": 1, "prompt": "upgrade"}
        assert Project.objects.count() == 1

    def test_the_limit_is_checked_before_the_warnings(self, company):
        Plan.objects.all().update(max_projects=0)
        _, client = sign_in(company)
        response = client.post(URL, body(job_description="short"), format="json")
        assert response.json()["error"]["code"] == "project_limit_reached"

    def test_an_admin_override_raises_the_limit(self, company):
        Plan.objects.all().update(max_projects=1)
        LimitOverride.objects.create(company=company, name="max_projects", value=3)
        _, client = sign_in(company)
        for title in ("A", "B", "C"):
            assert client.post(URL, body(title=title), format="json").status_code == 201
        assert client.post(URL, body(title="D"), format="json").status_code == 409

    def test_an_ended_subscription_shows_the_renewal_prompt(self):
        company = make_company()
        plan = make_plan()
        now = timezone.now()
        subs.activate(
            company.pk,
            plan,
            period_start=now - timezone.timedelta(days=60),
            period_end=now - timezone.timedelta(days=30),
        )
        subs.expire(company.pk)
        _, client = sign_in(company)
        response = client.post(URL, body(), format="json")
        assert response.status_code == 409
        assert response.json()["error"]["details"]["prompt"] == "renewal"

    def test_the_meter_counts_real_projects(self, company):
        from plans.summary import projects_in_use

        _, client = sign_in(company)
        client.post(URL, body(), format="json")
        assert projects_in_use(company.pk) == 1


class TestAnotherCompany:
    def test_a_project_always_belongs_to_the_creators_company(self, company):
        other = make_company()
        subscribe(other, Plan.objects.first())
        _, mine = sign_in(company)
        _, theirs = sign_in(other)
        mine_id = mine.post(URL, body(), format="json").json()["id"]
        theirs_id = theirs.post(URL, body(), format="json").json()["id"]
        assert Project.objects.get(pk=mine_id).company_id == company.pk
        assert Project.objects.get(pk=theirs_id).company_id == other.pk

    def test_the_project_limit_counts_only_the_own_company(self, company):
        Plan.objects.all().update(max_projects=1)
        other = make_company()
        subscribe(other, Plan.objects.first())
        _, theirs = sign_in(other)
        theirs.post(URL, body(), format="json")
        _, mine = sign_in(company)
        assert mine.post(URL, body(), format="json").status_code == 201
