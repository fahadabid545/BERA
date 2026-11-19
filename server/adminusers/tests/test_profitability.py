from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers import profitability
from ai.models import AiCall
from audit.models import AuditEvent
from core.tests.factories import make_admin_user, make_company
from plans.models import Plan, Subscription
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache, get_setting
from signin import service as signin

pytestmark = pytest.mark.django_db
URL = "/api/admin/cost-versus-revenue/"
RATE_URL = f"{URL}rate/"


def client_for(role):
    admin = make_admin_user(role=role)
    issued = signin.start_session(user_id=admin.pk, role=role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}"), admin


@pytest.fixture
def boss():
    return client_for("super")[0]


def make_plan(name="Fake Plan", usd="100.00", pkr="28000.00"):
    return Plan.objects.create(
        name=name,
        price_usd=None if usd is None else Decimal(usd),
        price_pkr=None if pkr is None else Decimal(pkr),
    )


def subscribe(company, plan, state="active", days_left=10):
    Subscription.objects.update_or_create(
        company=company,
        defaults={
            "plan": plan,
            "state": state,
            "period_start": timezone.now() - timedelta(days=20),
            "period_end": timezone.now() + timedelta(days=days_left),
            "renewal": True,
            "past_due_since": timezone.now() - timedelta(days=1) if state == "past_due" else None,
        },
    )


def spend(company, cost, ago=0):
    call = AiCall.objects.create(
        company=company, purpose="scoring", model="m", estimated_cost=Decimal(cost), duration_ms=1,
        result="ok",
    )  # fmt: skip
    AiCall.objects.filter(pk=call.pk).update(created_at=timezone.now() - timedelta(days=ago))


def set_rate_value(value):
    PlatformSetting.objects.update_or_create(key="billing.pkr_per_usd", defaults={"value": value})
    clear_cache()


def rows(client):
    response = client.get(URL)
    assert response.status_code == 200, response.content
    return response, {row["name"]: row for row in response.json()["results"]}


class TestAccess:
    def test_support_is_refused_and_so_is_a_visitor(self):
        support = client_for("support")[0]
        assert support.get(URL).status_code == 403
        assert support.put(RATE_URL, {}, format="json").status_code == 403
        assert APIClient().get(URL).status_code == 401

    def test_a_super_admin_may_open_it(self, boss):
        assert boss.get(URL).status_code == 200


class TestFigures:
    def test_a_paying_company_shows_amount_cost_and_margin(self, boss):
        company = make_company(name="Fake Alpha", country="US")
        subscribe(company, make_plan())
        spend(company, "10.250000")
        spend(company, "4.750000", ago=3)
        _, found = rows(boss)
        row = found["Fake Alpha"]
        assert (row["currency"], row["amount"], row["status"]) == ("USD", "100.00", "ok")
        assert row["paid_usd"] == "100.00"
        assert row["ai_cost"] == "15.000000"
        assert row["margin_percent"] == 85.0
        assert row["flagged"] is False

    def test_the_cost_matches_the_ai_call_records_in_the_window_only(self, boss):
        company = make_company(name="Fake Alpha", country="US")
        subscribe(company, make_plan())
        spend(company, "2")
        old = get_setting("admin_dashboard.margin_days") + 5
        spend(company, "50", ago=old)
        other = make_company(name="Fake Other", country="US")
        spend(other, "7")
        _, found = rows(boss)
        assert Decimal(found["Fake Alpha"]["ai_cost"]) == Decimal("2")
        assert Decimal(found["Fake Other"]["ai_cost"]) == Decimal("7")

    def test_a_margin_below_the_warning_level_is_flagged(self, boss):
        company = make_company(name="Fake Thin", country="US")
        subscribe(company, make_plan())
        spend(company, "81")
        _, found = rows(boss)
        assert found["Fake Thin"]["margin_percent"] == 19.0
        assert found["Fake Thin"]["flagged"] is True

    def test_exactly_the_warning_level_is_not_flagged(self, boss):
        company = make_company(name="Fake Edge", country="US")
        subscribe(company, make_plan())
        spend(company, "80")
        _, found = rows(boss)
        assert found["Fake Edge"]["margin_percent"] == 20.0
        assert found["Fake Edge"]["flagged"] is False

    def test_the_warning_level_is_a_platform_setting(self, boss):
        PlatformSetting.objects.create(key="profitability.warning_margin_percent", value=50)
        clear_cache()
        company = make_company(name="Fake Mid", country="US")
        subscribe(company, make_plan())
        spend(company, "60")
        response, found = rows(boss)
        assert found["Fake Mid"]["flagged"] is True
        assert response.json()["warning_margin_percent"] == 50

    def test_a_loss_is_a_negative_margin(self, boss):
        company = make_company(name="Fake Loss", country="US")
        subscribe(company, make_plan())
        spend(company, "150")
        _, found = rows(boss)
        assert found["Fake Loss"]["margin_percent"] == -50.0
        assert found["Fake Loss"]["flagged"] is True


class TestWhatCountsAsPaid:
    @pytest.mark.parametrize("state", ["active", "past_due", "cancelled"])
    def test_active_past_due_and_cancelled_count(self, boss, state):
        company = make_company(name="Fake Paying", country="US")
        subscribe(company, make_plan(), state=state)
        _, found = rows(boss)
        assert found["Fake Paying"]["paid_usd"] == "100.00"

    def test_past_due_beyond_the_grace_period_counts_as_expired(self, boss):
        company = make_company(name="Fake Late", country="US")
        subscribe(company, make_plan(), state="past_due")
        Subscription.objects.filter(company=company).update(
            past_due_since=timezone.now()
            - timedelta(days=get_setting("billing.past_due_grace_days") + 1)
        )
        _, found = rows(boss)
        assert found["Fake Late"]["subscription_state"] == "expired"
        assert found["Fake Late"]["paid_usd"] == "0.00"

    def test_a_free_grant_counts_as_zero_and_has_no_margin(self, boss):
        company = make_company(name="Fake Free", country="US")
        subscribe(company, make_plan(), state="granted_free")
        spend(company, "3")
        _, found = rows(boss)
        row = found["Fake Free"]
        assert (row["paid_usd"], row["margin_percent"], row["flagged"]) == ("0.00", None, False)
        assert row["ai_cost"] == "3.000000"

    def test_expired_and_unsubscribed_count_as_zero(self, boss):
        gone = make_company(name="Fake Gone", country="US")
        subscribe(gone, make_plan(), state="expired", days_left=-1)
        make_company(name="Fake Bare", country="US")
        _, found = rows(boss)
        assert found["Fake Gone"]["paid_usd"] == "0.00"
        assert found["Fake Bare"]["paid_usd"] == "0.00"
        assert found["Fake Bare"]["subscription_state"] == "no_plan"

    def test_amount_paid_is_one_function_of_the_subscription(self):
        company = make_company(country="PK")
        subscribe(company, make_plan())
        subscription = Subscription.objects.get(company=company)
        assert profitability.amount_paid(subscription, "active", "PK") == (
            "PKR",
            Decimal("28000.00"),
        )
        assert profitability.amount_paid(subscription, "active", "GB") == ("USD", Decimal("100.00"))
        assert profitability.amount_paid(subscription, "granted_free", "PK") == ("PKR", Decimal(0))


class TestCurrencyAndRate:
    def test_a_pakistani_company_is_converted_with_the_rate(self, boss):
        set_rate_value(280)
        company = make_company(name="Fake Karachi", country="PK")
        subscribe(company, make_plan())
        spend(company, "20")
        _, found = rows(boss)
        row = found["Fake Karachi"]
        assert (row["currency"], row["amount"], row["paid_usd"]) == ("PKR", "28000.00", "100.00")
        assert row["margin_percent"] == 80.0

    def test_without_a_rate_a_pkr_company_says_so_and_is_left_out_of_the_total(self, boss):
        pk = make_company(name="Fake Karachi", country="PK")
        us = make_company(name="Fake Austin", country="US")
        plan = make_plan()
        subscribe(pk, plan)
        subscribe(us, plan)
        spend(pk, "9")
        spend(us, "10")
        response, found = rows(boss)
        row = found["Fake Karachi"]
        assert (row["status"], row["paid_usd"], row["margin_percent"], row["flagged"]) == (
            "rate_not_set", None, None, False,
        )  # fmt: skip
        overall = response.json()["overall"]
        assert overall["paid_usd"] == "100.00"
        assert overall["ai_cost"] == "10.000000"
        assert overall["left_out"] == {"rate_not_set": 1, "no_price": 0}
        assert overall["all_ai_cost"] == "19.000000"
        assert response.json()["pkr_per_usd"] is None

    def test_a_plan_without_a_price_in_the_currency_shows_no_amount_and_no_margin(self, boss):
        pk = make_company(name="Fake Karachi", country="PK")
        us = make_company(name="Fake Austin", country="US")
        set_rate_value(280)
        subscribe(pk, make_plan(pkr=None))
        subscribe(us, make_plan(name="Other", usd=None))
        spend(pk, "5")
        response, found = rows(boss)
        for name in ("Fake Karachi", "Fake Austin"):
            row = found[name]
            assert (row["status"], row["amount"], row["paid_usd"], row["margin_percent"]) == (
                "no_price", None, None, None,
            )  # fmt: skip
            assert row["flagged"] is False
        assert response.json()["overall"]["left_out"]["no_price"] == 2
        assert response.json()["overall"]["companies_counted"] == 0

    def test_a_free_pakistani_company_without_a_rate_still_counts_as_zero(self, boss):
        company = make_company(name="Fake Free PK", country="PK")
        subscribe(company, make_plan(), state="granted_free")
        _, found = rows(boss)
        assert found["Fake Free PK"]["status"] == "ok"
        assert found["Fake Free PK"]["paid_usd"] == "0.00"


class TestOverall:
    def test_totals_add_up_the_counted_companies(self, boss):
        plan = make_plan()
        for index, cost in enumerate(["10", "30"]):
            company = make_company(name=f"Fake {index}", country="US")
            subscribe(company, plan)
            spend(company, cost)
        free = make_company(name="Fake Free", country="US")
        subscribe(free, plan, state="granted_free")
        spend(free, "10")
        response, _ = rows(boss)
        overall = response.json()["overall"]
        assert overall["paid_usd"] == "200.00"
        assert overall["ai_cost"] == "50.000000"
        assert overall["margin_percent"] == 75.0
        assert overall["flagged"] is False
        assert overall["companies_counted"] == 3

    def test_an_overall_margin_below_the_warning_level_is_flagged(self, boss):
        company = make_company(name="Fake Thin", country="US")
        subscribe(company, make_plan())
        spend(company, "90")
        response, _ = rows(boss)
        assert response.json()["overall"]["flagged"] is True

    def test_no_revenue_means_no_overall_margin(self, boss):
        make_company(name="Fake Bare", country="US")
        response, _ = rows(boss)
        assert response.json()["overall"]["margin_percent"] is None

    def test_the_worst_margins_come_first_and_companies_without_one_last(self, boss):
        plan = make_plan()
        for name, cost in [("Fake Good", "10"), ("Fake Bad", "90")]:
            company = make_company(name=name, country="US")
            subscribe(company, plan)
            spend(company, cost)
        make_company(name="Fake Aaa Bare", country="US")
        response, _ = rows(boss)
        names = [row["name"] for row in response.json()["results"]]
        assert names == ["Fake Bad", "Fake Good", "Fake Aaa Bare"]


class TestPaging:
    def test_pages_follow_the_platform_page_size(self, boss):
        PlatformSetting.objects.create(key="admin_companies.page_size", value=2)
        clear_cache()
        for index in range(5):
            make_company(name=f"Fake {index}", country="US")
        body = boss.get(f"{URL}?page=3").json()
        assert (body["total"], body["pages"], len(body["results"])) == (5, 3, 1)

    def test_a_bad_page_is_a_form_error(self, boss):
        response = boss.get(f"{URL}?page=abc")
        assert response.status_code == 400
        assert "page" in response.json()["error"]["fields"]


class TestSettingTheRate:
    def test_a_super_admin_sets_the_rate_and_it_is_audited(self):
        client, admin = client_for("super")
        response = client.put(
            RATE_URL, {"pkr_per_usd": "281.5", "reason": "Fake bank rate"}, format="json"
        )
        assert response.status_code == 200
        assert get_setting("billing.pkr_per_usd") == 281.5
        event = AuditEvent.objects.get(kind="admin.pkr_rate_changed")
        assert event.reason == "Fake bank rate"
        assert event.details["changes"]["pkr_per_usd"] == {"old": None, "new": "281.5000"}
        assert client.get(URL).json()["pkr_per_usd"] == "281.5"

    def test_changing_it_changes_the_conversion(self, boss):
        company = make_company(name="Fake Karachi", country="PK")
        subscribe(company, make_plan())
        boss.put(RATE_URL, {"pkr_per_usd": "280", "reason": "Fake"}, format="json")
        assert rows(boss)[1]["Fake Karachi"]["paid_usd"] == "100.00"
        boss.put(RATE_URL, {"pkr_per_usd": "140", "reason": "Fake"}, format="json")
        assert rows(boss)[1]["Fake Karachi"]["paid_usd"] == "200.00"

    def test_clearing_it_goes_back_to_not_set(self, boss):
        boss.put(RATE_URL, {"pkr_per_usd": "280", "reason": "Fake"}, format="json")
        response = boss.put(RATE_URL, {"pkr_per_usd": None, "reason": "Fake"}, format="json")
        assert response.status_code == 200
        assert get_setting("billing.pkr_per_usd") is None

    @pytest.mark.parametrize("value", ["0", "-5", "abc", True])
    def test_a_rate_that_is_not_a_positive_number_is_refused(self, boss, value):
        response = boss.put(RATE_URL, {"pkr_per_usd": value, "reason": "Fake"}, format="json")
        assert response.status_code == 400
        assert get_setting("billing.pkr_per_usd") is None

    def test_a_reason_is_required(self, boss):
        response = boss.put(RATE_URL, {"pkr_per_usd": "280"}, format="json")
        assert response.status_code == 400
        assert get_setting("billing.pkr_per_usd") is None
