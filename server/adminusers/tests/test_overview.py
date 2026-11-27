import csv
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from ai.models import AiCall
from companies.models import Company
from core.tests.factories import make_admin_user, make_company
from cvs.models import Candidate, CandidateScore, CvFile
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add
from plans.models import Plan, Subscription
from plans.payments import record_event  # noqa: E402
from signin import service

pytestmark = pytest.mark.django_db
URL = "/api/admin/dashboard/"


def admin_client(role="super"):
    admin = make_admin_user(role=role)
    issued = service.start_session(user_id=admin.pk, role=role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def boss():
    return admin_client("super")


@pytest.fixture
def helper():
    return admin_client("support")


def board(client, query=""):
    response = client.get(f"{URL}{query}")
    assert response.status_code == 200, response.content
    return response.json()


def behind(client, kind, key, query=""):
    return client.get(f"{URL}detail/?kind={kind}&key={key}{query}")


def stamp(model, queryset, days_ago):
    queryset.update(created_at=timezone.now() - timedelta(days=days_ago))


def ai_call(company, *, result="ok", cost="0.5", tokens=100, purpose="scoring", model="m", ago=0):
    call = AiCall.objects.create(
        company=company, purpose=purpose, model=model, tokens_in=tokens, tokens_out=tokens,
        estimated_cost=Decimal(cost), duration_ms=10, result=result,
        failure="" if result == "ok" else "provider_error",
    )  # fmt: skip
    AiCall.objects.filter(pk=call.pk).update(created_at=timezone.now() - timedelta(days=ago))
    return call


def set_subscription(company, **fields):
    Subscription.objects.filter(company=company).update(**fields)


class TestAccess:
    def test_it_needs_a_signed_in_admin(self):
        assert APIClient().get(URL).status_code == 401
        assert APIClient().get(f"{URL}detail/?kind=metric&key=companies").status_code == 401
        assert APIClient().get(f"{URL}report/").status_code == 401

    def test_a_company_user_is_refused(self):
        tenant = Tenant(make_plan())
        assert tenant.client.get(URL).status_code in (401, 403)

    def test_both_roles_may_open_it(self, boss, helper):
        assert board(boss)["role"] == "super"
        assert board(helper)["role"] == "support"

    def test_the_answer_names_the_refresh_delay_and_the_periods(self, boss):
        body = board(boss)
        assert body["refresh_seconds"] == 3 and body["days"] == 30
        assert body["choices"] == [1, 7, 30, 90, 180]

    @pytest.mark.parametrize("days", ["0", "5", "x"])
    def test_other_periods_are_refused(self, boss, days):
        response = boss.get(f"{URL}?days={days}")
        assert response.status_code == 400
        assert "days" in response.json()["error"]["fields"]


class TestWhatEachRoleSees:
    def test_support_gets_no_money_and_no_ai_figures_at_all(self, helper):
        tenant = Tenant(make_plan())
        add(tenant, "a.pdf", 80)
        ai_call(tenant.company)
        body = board(helper)
        assert "revenue" not in body and "ai" not in body
        assert "ai_cost" not in body["cards"]
        assert "ai_calls" not in body["usage"]["trend"]["metrics"]
        assert "failed_ai_calls" not in body["pending"]
        for row in body["usage"]["top_companies"]:
            assert "cost" not in row and "tokens" not in row
        assert "AI" not in str(body.keys())

    def test_a_super_admin_gets_everything(self, boss):
        tenant = Tenant(make_plan())
        add(tenant, "a.pdf", 80)
        ai_call(tenant.company)
        body = board(boss)
        assert {"revenue", "ai"} <= set(body)
        assert "ai_cost" in body["cards"] and "failed_ai_calls" in body["pending"]
        assert body["usage"]["top_companies"][0]["cost"] == 0.5

    def test_support_is_refused_what_is_behind_money_and_ai(self, helper):
        tenant = Tenant(make_plan())
        plan = Plan.objects.first()
        assert behind(helper, "plan", plan.pk).status_code == 403
        assert behind(helper, "pending", "failed_ai_calls").status_code == 403
        assert behind(helper, "ai_purpose", "scoring").status_code == 403
        assert behind(helper, "ai_model", "m").status_code == 403
        assert tenant

    def test_support_may_open_the_company_lists(self, helper):
        Tenant(make_plan())
        assert behind(helper, "metric", "companies").status_code == 200
        assert behind(helper, "state", "active").status_code == 200
        assert behind(helper, "pending", "past_due").status_code == 200

    def test_support_gets_the_report_without_money(self, helper):
        Tenant(make_plan())
        body = helper.get(f"{URL}report/").json()
        assert "revenue" not in body
        assert "AI cost (USD)" not in {row["metric"] for row in body["summary"]}
        text = helper.get(f"{URL}report/?as=csv").content.decode()
        assert "revenue" not in text.lower() and "AI cost" not in text


class TestCards:
    def test_new_companies_this_period_against_the_one_before(self, boss):
        for days_ago in (0, 1, 3):
            stamp(Company, Company.objects.filter(pk=make_company().pk), days_ago)
        stamp(Company, Company.objects.filter(pk=make_company().pk), 9)
        cards = board(boss, "?days=7")["cards"]
        assert (cards["companies"]["value"], cards["companies"]["previous"]) == (3, 1)
        assert cards["companies"]["change"] == 200.0
        assert len(cards["companies"]["series"]) == 7

    def test_cvs_scored_counts_every_company(self, boss):
        first, second = Tenant(make_plan()), Tenant(make_plan())
        add(first, "a.pdf", 80)
        add(second, "b.pdf", 70)
        assert board(boss)["cards"]["cvs_scored"]["value"] == 2

    def test_the_ai_cost_and_its_change(self, boss):
        company = make_company()
        ai_call(company, cost="3.00", ago=0)
        ai_call(company, cost="1.50", ago=1)
        ai_call(company, cost="1.50", ago=10)
        cards = board(boss, "?days=7")["cards"]
        assert (cards["ai_cost"]["value"], cards["ai_cost"]["previous"]) == (4.5, 1.5)
        assert cards["ai_cost"]["change"] == 200.0
        assert cards["ai_cost"]["series"][-1] == 3.0

    def test_an_empty_platform_has_zeros_and_no_change(self, boss):
        cards = board(boss)["cards"]
        assert cards["companies"]["value"] == 0 and cards["companies"]["change"] is None
        assert cards["ai_cost"]["value"] == 0

    def test_the_totals(self, boss):
        Tenant(make_plan())
        suspended = make_company()
        Company.objects.filter(pk=suspended.pk).update(status="suspended")
        assert board(boss)["totals"] == {"companies": 2, "suspended": 1, "paying": 1}


def pay(tenant, plan, amount, *, ago=0, kind="payment", currency="usd"):
    """A payment record, as the payment provider's notice writes it (amount in dollars)."""
    pay.count = getattr(pay, "count", 0) + 1
    return record_event(
        provider_event_id=f"evt_overview_{pay.count}",
        company_id=tenant.company.pk,
        kind=kind,
        amount_minor=int(Decimal(amount) * 100),
        currency=currency,
        occurred_at=timezone.now() - timedelta(days=ago),
        plan_id=plan.pk,
    )


class TestRevenue:
    def test_revenue_is_the_money_received_not_the_price_list(self, boss):
        plan = make_plan(price_usd=10)
        Tenant(plan), Tenant(plan)  # two paying subscriptions, nothing received yet
        revenue = board(boss)["revenue"]
        assert revenue["received"] == 0 and revenue["margin_percent"] is None

    def test_payments_in_the_days_are_added_up_by_plan(self, boss):
        cheap, dear = make_plan(name="Cheap", price_usd=10), make_plan(name="Dear", price_usd=50)
        one, two, three = Tenant(cheap), Tenant(cheap), Tenant(dear)
        pay(one, cheap, 10), pay(two, cheap, 10), pay(three, dear, 50)
        revenue = board(boss)["revenue"]
        assert revenue["received"] == 70.0
        assert [(r["name"], r["subscribers"], r["received"]) for r in revenue["plans"]] == [
            ("Dear", 1, 50.0),
            ("Cheap", 2, 20.0),
        ]
        assert {r["name"]: r["share"] for r in revenue["plans"]} == {"Dear": 71.4, "Cheap": 28.6}

    def test_refunds_are_taken_off(self, boss):
        plan = make_plan(price_usd=100)
        tenant = Tenant(plan)
        pay(tenant, plan, 100), pay(tenant, plan, 30, kind="refund")
        assert board(boss)["revenue"]["received"] == 70.0

    def test_failed_payments_bring_nothing(self, boss):
        plan = make_plan(price_usd=100)
        tenant = Tenant(plan)
        pay(tenant, plan, 100, kind="failure")
        assert board(boss)["revenue"]["received"] == 0

    def test_a_payment_outside_the_days_does_not_count(self, boss):
        plan = make_plan(price_usd=100)
        tenant = Tenant(plan)
        pay(tenant, plan, 100, ago=60)
        assert board(boss)["revenue"]["received"] == 0

    def test_only_dollars_are_added(self, boss):
        plan = make_plan(price_usd=100)
        tenant = Tenant(plan)
        pay(tenant, plan, 100), pay(tenant, plan, 9999, currency="pkr")
        assert board(boss)["revenue"]["received"] == 100.0

    def test_subscription_states_are_still_counted(self, boss):
        plan = make_plan(price_usd=10)
        free, ended, past_due, cancelled = (Tenant(plan) for _ in range(4))
        set_subscription(free.company, state="granted_free")
        set_subscription(ended.company, state="expired")
        set_subscription(past_due.company, state="past_due", past_due_since=timezone.now())
        set_subscription(cancelled.company, state="cancelled")
        revenue = board(boss)["revenue"]
        assert revenue["states"]["granted_free"] == 1 and revenue["states"]["expired"] == 1
        assert revenue["states"]["past_due"] == 1 and revenue["states"]["cancelled"] == 1

    def test_companies_with_no_subscription_row_count_as_no_plan(self, boss):
        make_company()
        assert board(boss)["revenue"]["states"]["no_plan"] == 1

    def test_the_margin_is_what_is_left_after_the_ai_cost(self, boss):
        plan = make_plan(price_usd=100)
        tenant = Tenant(plan)
        pay(tenant, plan, 100)
        ai_call(tenant.company, cost="25.00", ago=2)
        ai_call(tenant.company, cost="40.00", ago=60)  # too long ago for the margin
        revenue = board(boss)["revenue"]
        assert (revenue["received"], revenue["ai_cost"], revenue["margin_percent"]) == (
            100.0,
            25.0,
            75.0,
        )
        assert revenue["margin_days"] == 30

    def test_no_margin_without_revenue(self, boss):
        assert board(boss)["revenue"]["margin_percent"] is None

    def test_the_margin_window_comes_from_the_setting(self, boss):
        plan = make_plan(price_usd=100)
        tenant = Tenant(plan)
        pay(tenant, plan, 100, ago=60)
        ai_call(tenant.company, cost="40.00", ago=60)
        set_setting("admin_dashboard.margin_days", 90)
        assert board(boss)["revenue"]["margin_percent"] == 60.0


class TestRevenueHistory:
    def test_it_lists_the_months_with_money_received_against_ai_cost(self, boss):
        plan = make_plan(price_usd=100)
        tenant = Tenant(plan)
        pay(tenant, plan, 100), pay(tenant, plan, 50, ago=40)
        ai_call(tenant.company, cost="25.00")
        history = board(boss)["revenue"]["history"]
        assert len(history) == 12
        assert history[-1]["month"] == timezone.now().strftime("%Y-%m")
        assert (history[-1]["received"], history[-1]["ai_cost"]) == (100.0, 25.0)
        assert history[-1]["margin_percent"] == 75.0
        assert sum(row["received"] for row in history) == 150.0

    def test_a_month_without_payments_shows_zero_and_no_margin(self, boss):
        history = board(boss)["revenue"]["history"]
        assert all(row["received"] == 0 and row["margin_percent"] is None for row in history)

    def test_the_number_of_months_comes_from_the_setting(self, boss):
        set_setting("admin_dashboard.revenue_months", 3)
        assert len(board(boss)["revenue"]["history"]) == 3

    def test_support_admins_get_no_history(self, helper):
        assert "revenue" not in board(helper)


class TestUsage:
    def test_the_pace_of_scoring_over_time(self, boss):
        tenant = Tenant(make_plan())
        for index, days_ago in enumerate((0, 0, 1)):
            row = add(tenant, f"n{index}.pdf", 80, minutes=index)
            CandidateScore.objects.filter(candidate__cv_file=row).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
        metric = board(boss, "?days=7")["usage"]["trend"]["metrics"]["cvs_scored"]
        assert metric["total"] == 3 and metric["current"][-1] == 2 and len(metric["current"]) == 7
        assert metric["change_percent"] is None

    def test_the_companies_using_the_platform_most_best_first(self, boss):
        busy, quiet = Tenant(make_plan(name="Big")), Tenant(make_plan(name="Small"))
        for index in range(3):
            add(busy, f"b{index}.pdf", 80, minutes=index)
        add(quiet, "q.pdf", 70)
        ai_call(busy.company, cost="2.00", tokens=500)
        rows = board(boss)["usage"]["top_companies"]
        assert [row["cvs_scored"] for row in rows] == [3, 1]
        assert rows[0]["id"] == str(busy.company.pk) and rows[0]["plan"] == "Big"
        assert rows[0]["state"] == "active"
        assert (rows[0]["tokens"], rows[0]["cost"]) == (1000, 2.0)

    def test_how_many_are_listed_comes_from_the_setting(self, boss):
        for index in range(4):
            add(Tenant(make_plan()), f"c{index}.pdf", 50)
        set_setting("admin_dashboard.top_companies_count", 2)
        assert len(board(boss)["usage"]["top_companies"]) == 2


class TestAi:
    def test_calls_by_purpose_and_model_with_the_failure_rate(self, boss):
        company = make_company()
        ai_call(company, purpose="reading", model="small", cost="1")
        ai_call(company, purpose="scoring", model="big", cost="3")
        ai_call(company, purpose="scoring", model="big", cost="3", result="failed")
        ai_call(company, purpose="scoring", model="big", ago=60)
        ai = board(boss)["ai"]
        assert ai["calls"] == {"total": 3, "failed": 1, "failure_percent": 33.3}
        assert {row["purpose"]: row["count"] for row in ai["by_purpose"]} == {
            "reading": 1,
            "scoring": 2,
            "requirement_extraction": 0,
            "playground": 0,
            "ask": 0,
            "chatbot": 0,
            "support": 0,
        }
        assert ai["by_model"][0]["model"] == "big" and ai["by_model"][0]["cost"] == 6.0
        assert ai["by_model"][0]["calls"] == 2

    def test_no_failure_rate_without_calls(self, boss):
        assert board(boss)["ai"]["calls"]["failure_percent"] is None

    def test_the_tokens_used_are_summed_over_the_days(self, boss):
        tenant = Tenant(make_plan())
        ai_call(tenant.company, tokens=1000)
        tokens = board(boss)["ai"]["tokens"]
        assert tokens["used"] == 2000 and "cap" not in tokens

    def test_it_says_whether_ai_work_is_paused(self, boss):
        assert board(boss)["ai"]["control"]["paused"] is False


class TestPending:
    def test_what_waits_for_an_admin(self, boss):
        plan = make_plan()
        past_due, grant, later, suspended = (Tenant(plan) for _ in range(4))
        set_subscription(past_due.company, state="past_due", past_due_since=timezone.now())
        set_subscription(
            grant.company, state="granted_free", period_end=timezone.now() + timedelta(days=3)
        )
        set_subscription(
            later.company, state="granted_free", period_end=timezone.now() + timedelta(days=30)
        )
        Company.objects.filter(pk=suspended.company.pk).update(status="suspended")
        ai_call(grant.company, result="failed")
        ai_call(grant.company, result="failed", ago=3)
        pending = board(boss)["pending"]
        assert pending == {
            "past_due": 1, "grants_expiring": 1, "suspended": 1,
            "failed_ai_calls": 1, "failed_jobs": 0, "data_requests": 0, "feedback": 0,
        }  # fmt: skip

    def test_the_windows_come_from_the_settings(self, boss):
        tenant = Tenant(make_plan())
        set_subscription(
            tenant.company, state="granted_free", period_end=timezone.now() + timedelta(days=30)
        )
        ai_call(tenant.company, result="failed", ago=3)
        set_setting("admin_dashboard.expiring_grant_days", 60)
        set_setting("admin_dashboard.failed_calls_hours", 100)
        pending = board(boss)["pending"]
        assert pending["grants_expiring"] == 1 and pending["failed_ai_calls"] == 1


class TestRecent:
    def test_the_newest_companies_first_up_to_the_limit(self, boss):
        names = []
        for index in range(3):
            company = make_company()
            stamp(Company, Company.objects.filter(pk=company.pk), 3 - index)
            names.append(company.name)
        set_setting("admin_dashboard.recent_companies_count", 2)
        recent = board(boss)["recent"]
        assert [row["name"] for row in recent] == [names[2], names[1]]
        assert recent[0]["state"] == "no_plan" and recent[0]["plan"] is None


class TestDetail:
    def test_new_companies_of_the_period(self, boss):
        stamp(Company, Company.objects.filter(pk=(old := make_company()).pk), 40)
        fresh = make_company()
        found = behind(boss, "metric", "companies", "&days=7").json()
        assert found["total"] == 1 and found["items"][0]["id"] == str(fresh.pk)
        assert found["items"][0]["type"] == "company" and old

    def test_the_cvs_scored_card_lists_the_companies_using_it_most(self, boss):
        add(Tenant(make_plan()), "a.pdf", 80)
        found = behind(boss, "metric", "cvs_scored").json()
        assert found["total"] == 1 and found["items"][0]["cvs_scored"] == 1

    def test_the_companies_of_a_subscription_state(self, boss):
        active, expired = Tenant(make_plan()), Tenant(make_plan())
        set_subscription(expired.company, state="expired")
        found = behind(boss, "state", "active").json()
        assert [item["id"] for item in found["items"]] == [str(active.company.pk)]
        none = make_company()
        assert str(none.pk) in {i["id"] for i in behind(boss, "state", "no_plan").json()["items"]}

    def test_the_paying_companies_of_a_plan(self, boss):
        plan = make_plan(name="Gold")
        tenant = Tenant(plan)
        Tenant(make_plan(name="Other"))
        found = behind(boss, "plan", plan.pk).json()
        assert [item["id"] for item in found["items"]] == [str(tenant.company.pk)]
        assert found["items"][0]["plan"] == "Gold"

    def test_an_unknown_plan_is_not_found(self, boss):
        assert behind(boss, "plan", 999999).status_code == 404
        assert behind(boss, "plan", "x").status_code == 404

    def test_each_pending_group_lists_its_companies(self, boss):
        plan = make_plan()
        past_due, grant, suspended = (Tenant(plan) for _ in range(3))
        set_subscription(past_due.company, state="past_due", past_due_since=timezone.now())
        set_subscription(
            grant.company, state="granted_free", period_end=timezone.now() + timedelta(days=2)
        )
        Company.objects.filter(pk=suspended.company.pk).update(status="suspended")
        for key, tenant in (
            ("past_due", past_due),
            ("grants_expiring", grant),
            ("suspended", suspended),
        ):
            found = behind(boss, "pending", key).json()
            assert [item["id"] for item in found["items"]] == [str(tenant.company.pk)]

    def test_failed_ai_calls_and_the_calls_behind_a_purpose_or_model(self, boss):
        company = make_company()
        ai_call(company, result="failed", purpose="reading", model="small")
        ai_call(company, purpose="scoring", model="big")
        failed = behind(boss, "pending", "failed_ai_calls").json()
        assert failed["total"] == 1 and failed["items"][0]["type"] == "ai_call"
        assert failed["items"][0]["failure"] == "provider_error"
        assert behind(boss, "ai_purpose", "scoring").json()["total"] == 1
        assert behind(boss, "ai_model", "small").json()["total"] == 1
        item = behind(boss, "ai_model", "big").json()["items"][0]
        assert "prompt" not in item and item["tokens"] == 200 and item["cost"] == 0.5

    def test_the_list_is_cut_at_the_setting_but_the_total_is_real(self, boss):
        for _ in range(4):
            make_company()
        set_setting("dashboard.detail_limit", 2)
        found = behind(boss, "metric", "companies").json()
        assert found["total"] == 4 and len(found["items"]) == 2

    @pytest.mark.parametrize(
        ("kind", "key"),
        [("nope", "x"), ("state", "nope"), ("pending", "nope"), ("metric", "nope"), ("", ""),
         ("ai_model", "")],
    )  # fmt: skip
    def test_unknown_things_are_refused(self, boss, kind, key):
        assert behind(boss, kind, key).status_code == 400

    def test_the_period_is_checked(self, boss):
        assert behind(boss, "metric", "companies", "&days=5").status_code == 400


class TestReport:
    def test_the_numbers_as_a_table(self, boss):
        gold = make_plan(name="Gold", price_usd=40)
        tenant = Tenant(gold)
        pay(tenant, gold, 40)
        add(tenant, "a.pdf", 80)
        ai_call(tenant.company, cost="4")
        body = boss.get(f"{URL}report/?days=7").json()
        summary = {row["metric"]: row for row in body["summary"]}
        assert summary["CVs scored"]["current"] == 1 and summary["AI cost (USD)"]["current"] == 4.0
        assert body["revenue"]["received"] == 40.0 and body["revenue"]["margin_percent"] == 90.0
        assert body["revenue"]["plans"] == [{"plan": "Gold", "subscribers": 1, "received": 40.0}]
        assert len(body["revenue"]["history"]) == 12
        assert body["companies"][0]["cvs_scored"] == 1

    def test_the_file_is_csv_and_guards_formula_like_names(self, boss):
        tenant = Tenant(make_plan())
        Company.objects.filter(pk=tenant.company.pk).update(name="=HYPERLINK(1)")
        add(tenant, "a.pdf", 80)
        response = boss.get(f"{URL}report/?as=csv")
        assert response["Content-Type"].startswith("text/csv")
        assert "attachment" in response["Content-Disposition"]
        text = response.content.decode()
        assert "'=HYPERLINK(1)" in text and "\n=HYPERLINK" not in text
        rows = list(csv.reader(io.StringIO(text)))
        assert ["Company", "Plan", "Subscription", "CVs scored", "AI cost (USD)"] in rows

    def test_the_period_is_checked(self, boss):
        assert boss.get(f"{URL}report/?days=5").status_code == 400


class TestCost:
    def test_the_query_count_does_not_grow_with_companies(self, boss):
        plan = make_plan()
        for index in range(3):
            tenant = Tenant(plan)
            add(tenant, f"x{index}.pdf", 50)
            ai_call(tenant.company)
        board(boss)  # the platform settings are read once and kept
        with CaptureQueriesContext(connection) as small:
            board(boss)
        for index in range(8):
            tenant = Tenant(plan)
            add(tenant, f"y{index}.pdf", 50 + index)
            ai_call(tenant.company)
        with CaptureQueriesContext(connection) as large:
            board(boss)
        assert len(large) == len(small)


def test_unused_imports_stay_used():
    assert Candidate and CvFile
