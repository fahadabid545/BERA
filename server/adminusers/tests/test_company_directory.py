import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.service import record
from companies.models import CompanyUser
from core.tests.factories import make_admin_user, make_company, make_company_user
from cvs.models import CvFile
from plans import subscriptions as subs
from plans.models import LimitOverride, Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project
from signin import service as signin
from usage import service as usage

pytestmark = pytest.mark.django_db
LIST = "/api/admin/companies/"
CANDIDATE_TEXT = "Fake Candidate Fakename"
DESCRIPTION_TEXT = "Fake confidential job description"


def client_for(admin):
    issued = signin.start_session(user_id=admin.pk, role=admin.role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def boss():
    return client_for(make_admin_user(role="super"))


@pytest.fixture
def helper():
    return client_for(make_admin_user(role="support"))


def make_plan(name="Fake Plan", cvs=10):
    return Plan.objects.create(
        name=name,
        status="active",
        price_usd=Decimal("10"),
        cvs_per_month=cvs,
        cvs_per_project=cvs,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
    )


def subscribed(plan=None, **company_fields):
    company = make_company(**company_fields)
    make_company_user(company, role="owner")
    if plan:
        subs.activate(
            company.pk,
            plan,
            period_start=timezone.now(),
            period_end=timezone.now() + timezone.timedelta(days=30),
        )
    return company


def score_cvs(company, count):
    for _ in range(count):
        cv_id = uuid.uuid4()
        usage.accept_cv(company.pk, cv_id)
        usage.mark_scored(company.pk, cv_id)


def names(response):
    return [row["name"] for row in response.json()["results"]]


class TestWhoMayOpen:
    def test_both_roles_may_open_the_list_and_a_page(self, boss, helper):
        company = subscribed()
        for client in (boss, helper):
            assert client.get(LIST).status_code == 200
            assert client.get(f"{LIST}{company.pk}/").status_code == 200

    def test_a_company_user_and_a_visitor_are_refused(self):
        company = subscribed()
        owner = company.users.get()
        issued = signin.start_session(
            user_id=owner.pk, role=owner.role, company_id=company.pk, kind="company"
        )
        as_company = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert as_company.get(LIST).status_code in (401, 403)
        assert APIClient().get(LIST).status_code in (401, 403)

    def test_an_unknown_company_is_not_found(self, boss):
        assert boss.get(f"{LIST}999999/").status_code == 404
        assert boss.get(f"{LIST}not-a-number/").status_code == 404


class TestList:
    def test_each_row_has_its_facts(self, boss):
        plan = make_plan()
        company = subscribed(plan, name="Fake Alpha Ltd", country="GB")
        score_cvs(company, 3)
        row = boss.get(LIST).json()["results"][0]
        assert row["name"] == "Fake Alpha Ltd"
        assert row["country"] == "GB"
        assert row["status"] == "active"
        assert row["plan_name"] == "Fake Plan"
        assert row["subscription_state"] == "active"
        assert (row["cvs_used"], row["cvs_limit"]) == (3, 10)
        assert row["users"] == 1

    def test_search_by_name(self, boss):
        subscribed(name="Fake Alpha Ltd")
        subscribed(name="Fake Beta Ltd")
        assert names(boss.get(LIST, {"search": "beta"})) == ["Fake Beta Ltd"]

    def test_filter_by_status(self, boss):
        subscribed(name="Fake Alpha Ltd")
        subscribed(name="Fake Beta Ltd", status="suspended")
        assert names(boss.get(LIST, {"status": "suspended"})) == ["Fake Beta Ltd"]

    def test_filter_by_country(self, boss):
        subscribed(name="Fake Alpha Ltd", country="GB")
        subscribed(name="Fake Beta Ltd", country="DE")
        assert names(boss.get(LIST, {"country": "de"})) == ["Fake Beta Ltd"]

    def test_filter_by_plan_and_by_no_plan(self, boss):
        small, large = make_plan("Fake Small"), make_plan("Fake Large")
        subscribed(small, name="Fake Alpha Ltd")
        subscribed(large, name="Fake Beta Ltd")
        subscribed(name="Fake Gamma Ltd")
        assert names(boss.get(LIST, {"plan": str(large.pk)})) == ["Fake Beta Ltd"]
        assert names(boss.get(LIST, {"plan": "none"})) == ["Fake Gamma Ltd"]

    def test_the_list_offers_the_plans_to_filter_by(self, boss):
        made = make_plan("Fake Small")
        offered = boss.get(LIST).json()["plans"]
        assert {"id": str(made.pk), "name": "Fake Small"} in offered

    def test_filters_combine(self, boss):
        plan = make_plan()
        subscribed(plan, name="Fake Alpha Ltd", country="GB")
        subscribed(plan, name="Fake Beta Ltd", country="DE")
        found = boss.get(LIST, {"plan": str(plan.pk), "country": "GB", "status": "active"})
        assert names(found) == ["Fake Alpha Ltd"]

    def test_unknown_filter_values_are_refused(self, boss):
        for params in ({"status": "x"}, {"usage": "x"}, {"plan": "x"}, {"page": "x"}):
            response = boss.get(LIST, params)
            assert response.status_code == 400
            assert response.json()["error"]["fields"]

    def test_paging(self, boss):
        PlatformSetting.objects.create(key="admin_companies.page_size", value=2)
        clear_cache()
        for number in range(3):
            subscribed(name=f"Fake Company {number}")
        first = boss.get(LIST).json()
        second = boss.get(LIST, {"page": 2}).json()
        assert (first["total"], first["pages"]) == (3, 2)
        assert names(boss.get(LIST)) == ["Fake Company 0", "Fake Company 1"]
        assert [row["name"] for row in second["results"]] == ["Fake Company 2"]


class TestUsageFilter:
    @pytest.fixture
    def companies(self):
        plan = make_plan(cvs=10)
        made = {}
        for name, used in (("Under", 2), ("Between", 8), ("Reached", 10)):
            made[name] = subscribed(plan, name=f"Fake {name} Ltd")
            score_cvs(made[name], used)
        return made

    def test_under_80_percent(self, boss, companies):
        assert names(boss.get(LIST, {"usage": "under"})) == ["Fake Under Ltd"]

    def test_80_to_99_percent(self, boss, companies):
        assert names(boss.get(LIST, {"usage": "between"})) == ["Fake Between Ltd"]

    def test_100_percent_reached(self, boss, companies):
        assert names(boss.get(LIST, {"usage": "reached"})) == ["Fake Reached Ltd"]

    def test_every_row_still_shows_its_cv_count(self, boss, companies):
        rows = {row["name"]: row["cvs_used"] for row in boss.get(LIST).json()["results"]}
        assert rows == {"Fake Under Ltd": 2, "Fake Between Ltd": 8, "Fake Reached Ltd": 10}

    def test_an_override_counts_instead_of_the_plan_value(self, boss, companies):
        LimitOverride.objects.create(company=companies["Under"], name="cvs_per_month", value=2)
        assert names(boss.get(LIST, {"usage": "reached"})) == [
            "Fake Reached Ltd",
            "Fake Under Ltd",
        ]

    def test_a_company_with_no_plan_is_left_out(self, boss, companies):
        subscribed(name="Fake No Plan Ltd")
        for level in ("under", "between", "reached"):
            assert "Fake No Plan Ltd" not in names(boss.get(LIST, {"usage": level}))
        assert "Fake No Plan Ltd" in names(boss.get(LIST))

    def test_an_expired_company_is_left_out(self, boss, companies):
        subs.expire(companies["Under"].pk)
        assert names(boss.get(LIST, {"usage": "under"})) == []

    def test_a_company_with_no_cv_limit_is_left_out(self, boss, companies):
        LimitOverride.objects.create(company=companies["Under"], name="cvs_per_month", value=0)
        assert names(boss.get(LIST, {"usage": "under"})) == []


class TestCompanyPage:
    @pytest.fixture
    def company(self):
        company = subscribed(make_plan(), name="Fake Alpha Ltd", country="GB")
        make_company_user(company, role="member", email_verified=True)
        score_cvs(company, 3)
        return company

    def test_it_shows_the_company_users_subscription_and_usage(self, boss, company):
        page = boss.get(f"{LIST}{company.pk}/").json()
        assert page["company"]["name"] == "Fake Alpha Ltd"
        assert page["company"]["status"] == "active"
        assert sorted(person["role"] for person in page["users"]) == ["member", "owner"]
        assert page["subscription"]["plan_name"] == "Fake Plan"
        assert page["subscription"]["state"] == "active"
        assert page["usage"]["cvs"]["used"] == 3
        assert page["usage"]["cvs"]["limit"] == 10

    def test_it_counts_active_and_archived_projects(self, boss, company):
        make_project(company, "Fake Open")
        make_project(company, "Fake Old", status="archived")
        counts = boss.get(f"{LIST}{company.pk}/").json()["project_counts"]
        assert counts == {"active": 1, "archived": 1}

    def test_each_project_shows_its_pinned_reading_setup_to_both_roles(self, boss, helper, company):
        make_project(company, "Fake Open", reading_model="fake-reader", reading_prompt_version=7)
        for client in (boss, helper):
            project = client.get(f"{LIST}{company.pk}/").json()["projects"][0]
            assert project["title"] == "Fake Open"
            assert project["reading_model"] == "fake-reader"
            assert project["reading_prompt_version"] == 7

    def test_the_history_is_this_companys_audit_entries_newest_first(self, boss, company):
        other = subscribed(name="Fake Other Ltd")
        record("admin.company_suspended", target=company, reason="Fake first reason")
        record("admin.company_unsuspended", target=company, reason="Fake second reason")
        record("admin.company_suspended", target=other, reason="Fake other reason")
        history = boss.get(f"{LIST}{company.pk}/").json()["history"]
        kinds = [entry["kind"] for entry in history if entry["kind"].startswith("admin.")]
        assert kinds == ["admin.company_unsuspended", "admin.company_suspended"]
        assert history[0]["reason"] == "Fake second reason"

    def test_the_history_is_limited(self, boss, company):
        PlatformSetting.objects.create(key="admin_companies.detail_limit", value=1)
        clear_cache()
        record("admin.company_suspended", target=company, reason="Fake reason")
        record("admin.company_unsuspended", target=company, reason="Fake reason")
        assert len(boss.get(f"{LIST}{company.pk}/").json()["history"]) == 1

    def test_the_ai_cost_is_for_super_admins_only(self, boss, helper, company):
        assert "estimated_cost" in boss.get(f"{LIST}{company.pk}/").json()["usage"]
        assert "estimated_cost" not in helper.get(f"{LIST}{company.pk}/").json()["usage"]

    def test_a_company_with_no_plan_still_opens(self, boss):
        company = subscribed(name="Fake Bare Ltd")
        page = boss.get(f"{LIST}{company.pk}/").json()
        assert page["subscription"]["plan_name"] is None
        assert page["usage"]["cvs"]["limit"] == 0


class TestNoCandidateContent:
    def test_nothing_from_a_cv_or_a_job_description_reaches_either_role(self, boss, helper):
        company = subscribed(make_plan(), name="Fake Alpha Ltd")
        project = make_project(company, "Fake Open", job_description=DESCRIPTION_TEXT)
        CvFile.objects.create(
            company=company,
            project=project,
            original_name=f"{CANDIDATE_TEXT}.pdf",
            file_type="pdf",
            size_bytes=10,
            storage_key="fake/key",
            uploaded_by=company.users.get(role="owner"),
        )
        for client in (boss, helper):
            for path in (LIST, f"{LIST}{company.pk}/"):
                body = client.get(path).content.decode()
                assert CANDIDATE_TEXT not in body
                assert DESCRIPTION_TEXT not in body


def make_project(company, title, **fields):
    owner = CompanyUser.objects.get(company=company, role="owner")
    return Project.objects.create(
        **{
            "company": company,
            "title": title,
            "job_description": "Fake description",
            "reading_model": "fake-model",
            "scoring_model": "fake-model",
            "reading_prompt_version": 1,
            "scoring_prompt_version": 1,
            "created_by": owner,
            **fields,
        }
    )
