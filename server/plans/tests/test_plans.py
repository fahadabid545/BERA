from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.tests.factories import make_admin_user
from plans import service
from plans.models import PendingPlanChange, Plan
from signin import service as signin

URL = "/api/admin/plans/"
REASON = "Fake reason for the test."
pytestmark = pytest.mark.django_db

FULL = {
    "name": "Fake Plan",
    "description": "A short fake description",
    "price_usd": 10,
    "price_pkr": 3000,
    "cvs_per_month": 100,
    "cvs_per_project": 50,
    "max_projects": 5,
    "max_team_accounts": 3,
    "max_top_n": 10,
    "monthly_ai_token_cap": 1_000_000,
    "status": "active",
    "display_order": 1,
}


def client_for(role="super"):
    admin = make_admin_user(role=role)
    issued = signin.start_session(user_id=admin.pk, role=role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}"), admin


@pytest.fixture
def boss():
    return client_for("super")


def create(client, **fields):
    return client.post(URL, {**FULL, **fields}, format="json")


def edit(client, plan_id, **fields):
    body = {"reason": REASON, **fields}
    return client.patch(f"{URL}{plan_id}/", body, format="json")


def subscribers(count):
    return patch("plans.service.subscriber_count", return_value=count)


class TestTheStartingPlans:
    def test_three_plans_exist_hidden_with_the_agreed_prices_and_cv_counts(self):
        starter, growth, scale = Plan.objects.order_by("display_order")
        assert (starter.cvs_per_month, starter.price_pkr) == (250, Decimal("3000.00"))
        assert (growth.cvs_per_month, growth.price_pkr) == (500, Decimal("5000.00"))
        assert (scale.cvs_per_month, scale.price_pkr) == (None, Decimal("7000.00"))
        for plan in (starter, growth, scale):
            assert plan.status == "hidden" and plan.price_usd is None
            assert plan.max_projects is None and plan.monthly_ai_token_cap is None

    def test_they_cannot_be_made_active_until_every_number_is_filled_in(self, boss):
        client, _ = boss
        starter = Plan.objects.get(display_order=1)
        response = edit(client, starter.pk, status="active")
        assert (response.status_code, response.json()["error"]["code"]) == (400, "plan_incomplete")
        assert "price_usd" in response.json()["error"]["fields"]
        assert "cvs_per_month" not in response.json()["error"]["fields"]  # already set
        starter.refresh_from_db()
        assert starter.status == "hidden"

    def test_they_become_active_once_complete_and_can_be_renamed(self, boss):
        client, _ = boss
        starter = Plan.objects.get(display_order=1)
        response = edit(
            client,
            starter.pk,
            name="Lite",
            status="active",
            price_usd=9.99,
            cvs_per_project=50,
            max_projects=5,
            max_team_accounts=3,
            max_top_n=10,
            monthly_ai_token_cap=500000,
        )
        assert response.status_code == 200
        starter.refresh_from_db()
        assert (starter.name, starter.status, starter.price_usd) == (
            "Lite",
            "active",
            Decimal("9.99"),
        )


class TestCreatingAndListing:
    def test_a_super_admin_creates_a_plan_with_every_field(self, boss):
        client, _ = boss
        response = create(client)
        assert response.status_code == 201
        body = response.json()
        assert body["price_usd"] == "10.00" and body["price_pkr"] == "3000.00"
        assert body["status"] == "active" and body["subscribers"] == 0
        plan = Plan.objects.get(pk=body["id"])
        assert (plan.cvs_per_month, plan.max_team_accounts, plan.display_order) == (100, 3, 1)

    def test_a_new_plan_is_hidden_unless_it_says_otherwise(self, boss):
        client, _ = boss
        assert client.post(URL, {"name": "Draft"}, format="json").json()["status"] == "hidden"

    def test_a_plan_without_a_pkr_price_is_fine(self, boss):
        client, _ = boss
        assert create(client, price_pkr=None).status_code == 201

    def test_the_list_holds_every_plan_in_display_order(self, boss):
        client, _ = boss
        create(client, name="Last", display_order=99, status="archived")
        rows = client.get(URL).json()
        assert [r["display_order"] for r in rows] == sorted(r["display_order"] for r in rows)
        assert rows[-1]["name"] == "Last" and rows[-1]["status"] == "archived"

    def test_a_single_plan_can_be_read_and_an_unknown_one_is_not_found(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        assert client.get(f"{URL}{plan_id}/").json()["name"] == "Fake Plan"
        for missing in (999999, "abc"):
            assert client.get(f"{URL}{missing}/").status_code == 404

    def test_creating_is_written_to_the_audit_log_with_the_values(self, boss):
        client, admin = boss
        plan_id = create(client).json()["id"]
        entry = AuditEvent.objects.get(kind="admin.plan_created")
        assert (entry.actor_kind, entry.actor_id) == ("admin", admin.pk)
        assert entry.details["plan_id"] == plan_id
        assert entry.details["changes"]["price_usd"] == {"old": None, "new": "10.00"}


class TestTheNumbers:
    @pytest.mark.parametrize(
        "field",
        [
            "cvs_per_month",
            "cvs_per_project",
            "max_projects",
            "max_team_accounts",
            "max_top_n",
            "monthly_ai_token_cap",
        ],
    )
    @pytest.mark.parametrize("bad", [0, -1, 2.5, "7", True, 3_000_000_000])
    def test_limits_are_positive_whole_numbers(self, boss, field, bad):
        client, _ = boss
        assert create(client, **{field: bad}).status_code == 400

    @pytest.mark.parametrize("field", ["price_usd", "price_pkr"])
    @pytest.mark.parametrize("bad", [0, -5, 10.999, "12.345", True, "abc", [1]])
    def test_prices_are_positive_with_two_decimals(self, boss, field, bad):
        client, _ = boss
        assert create(client, **{field: bad}).status_code == 400

    @pytest.mark.parametrize("good", [1, 10, 10.5, 19.99, "7.25"])
    def test_prices_with_up_to_two_decimals_are_kept_exactly(self, boss, good):
        client, _ = boss
        body = create(client, price_usd=good).json()
        assert body["price_usd"] == f"{Decimal(str(good)):.2f}"

    def test_unknown_fields_and_bad_status_are_refused(self, boss):
        client, _ = boss
        assert create(client, rollover=True).status_code == 400
        assert create(client, status="deleted").status_code == 400
        assert create(client, name="").status_code == 400
        assert create(client, name="x" * 101).status_code == 400
        assert not Plan.objects.filter(name="x" * 101).exists()


class TestStatuses:
    def test_a_plan_can_be_hidden_archived_and_made_active_again(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        for status in ("hidden", "archived", "active"):
            assert edit(client, plan_id, status=status).json()["status"] == status

    def test_only_active_plans_are_offered_for_buying(self, boss):
        client, _ = boss
        active = create(client, name="On sale").json()["id"]
        create(client, name="Hidden one", status="hidden")
        create(client, name="Old one", status="archived")
        assert list(service.active_plans().values_list("pk", flat=True)) == [active]

    def test_active_plans_follow_the_display_order(self, boss):
        client, _ = boss
        second = create(client, name="B", display_order=2).json()["id"]
        first = create(client, name="A", display_order=1).json()["id"]
        assert list(service.active_plans().values_list("pk", flat=True)) == [first, second]

    def test_an_active_plan_cannot_lose_a_needed_number(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        response = edit(client, plan_id, max_projects=None)
        assert response.json()["error"]["code"] == "plan_incomplete"
        assert Plan.objects.get(pk=plan_id).max_projects == 5


class TestSubscribers:
    def test_without_subscribers_a_change_applies_at_once(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        response = edit(client, plan_id, cvs_per_month=200)
        assert response.json()["waiting_for_renewal"] is False
        assert Plan.objects.get(pk=plan_id).cvs_per_month == 200
        assert not PendingPlanChange.objects.exists()

    def test_with_subscribers_price_and_limits_wait_for_the_next_renewal(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(4):
            response = edit(client, plan_id, cvs_per_month=200, price_usd=12)
        body = response.json()
        assert body["waiting_for_renewal"] is True
        assert (body["cvs_per_month"], body["price_usd"]) == (100, "10.00")  # unchanged for now
        assert body["pending_change"] == {"cvs_per_month": 200, "price_usd": "12.00"}

    def test_the_waiting_change_is_applied_at_renewal(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(4):
            edit(client, plan_id, cvs_per_month=200, price_usd=12)
        plan = service.apply_pending_change(Plan.objects.get(pk=plan_id))
        assert (plan.cvs_per_month, plan.price_usd) == (200, Decimal("12.00"))
        assert not PendingPlanChange.objects.exists()
        assert service.apply_pending_change(plan) == plan  # nothing left to apply

    def test_the_admin_can_choose_to_apply_now(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(4):
            response = edit(client, plan_id, cvs_per_month=200, apply="now")
        assert response.json()["waiting_for_renewal"] is False
        assert Plan.objects.get(pk=plan_id).cvs_per_month == 200

    def test_a_newer_waiting_edit_replaces_the_same_field_and_keeps_the_others(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(2):
            edit(client, plan_id, cvs_per_month=200, max_projects=9)
            edit(client, plan_id, cvs_per_month=300)
        assert PendingPlanChange.objects.get().values == {"cvs_per_month": 300, "max_projects": 9}

    def test_name_description_order_and_status_apply_at_once_even_with_subscribers(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(4):
            response = edit(client, plan_id, name="Renamed", status="hidden", display_order=7)
        assert response.json()["waiting_for_renewal"] is False
        plan = Plan.objects.get(pk=plan_id)
        assert (plan.name, plan.status, plan.display_order) == ("Renamed", "hidden", 7)

    def test_a_mixed_edit_applies_the_immediate_part_and_holds_back_the_rest(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(4):
            edit(client, plan_id, name="Renamed", price_usd=12)
        plan = Plan.objects.get(pk=plan_id)
        assert (plan.name, plan.price_usd) == ("Renamed", Decimal("10.00"))
        assert PendingPlanChange.objects.get().values == {"price_usd": "12.00"}

    def test_a_plan_with_subscribers_can_be_archived_but_not_deleted(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(4):
            assert edit(client, plan_id, status="archived").json()["status"] == "archived"
            response = client.delete(f"{URL}{plan_id}/", {"reason": REASON}, format="json")
        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "plan_has_subscribers",
        )
        assert Plan.objects.filter(pk=plan_id).exists()

    def test_a_plan_without_subscribers_can_be_deleted(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        response = client.delete(f"{URL}{plan_id}/", {"reason": REASON}, format="json")
        assert response.status_code == 204 and not Plan.objects.filter(pk=plan_id).exists()
        assert AuditEvent.objects.filter(kind="admin.plan_deleted").count() == 1

    def test_changing_nothing_is_said_plainly(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        response = edit(client, plan_id, name="Fake Plan")
        assert response.json()["error"]["code"] == "nothing_changed"


class TestTheAuditLog:
    def test_a_change_is_written_with_who_why_and_old_and_new_values(self, boss):
        client, admin = boss
        plan_id = create(client).json()["id"]
        edit(client, plan_id, price_usd=12.5, status="hidden")
        entry = AuditEvent.objects.get(kind="admin.plan_changed")
        assert (entry.actor_kind, entry.actor_id, entry.reason) == ("admin", admin.pk, REASON)
        assert entry.details["changes"] == {
            "price_usd": {"old": "10.00", "new": "12.50"},
            "status": {"old": "active", "new": "hidden"},
        }
        assert entry.details["plan_id"] == plan_id and entry.details["applies"] == "now"

    def test_a_change_that_waits_says_so_and_still_shows_old_and_new(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        with subscribers(1):
            edit(client, plan_id, max_projects=9)
        entry = AuditEvent.objects.get(kind="admin.plan_changed")
        assert entry.details["applies"] == "renewal"
        assert entry.details["changes"] == {"max_projects": {"old": 5, "new": 9}}

    def test_without_a_reason_nothing_changes(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        for reason in ("", "   "):
            response = client.patch(
                f"{URL}{plan_id}/", {"reason": reason, "name": "X"}, format="json"
            )
            assert response.status_code == 400
        assert client.patch(f"{URL}{plan_id}/", {"name": "X"}, format="json").status_code == 400
        assert Plan.objects.get(pk=plan_id).name == "Fake Plan"
        assert not AuditEvent.objects.filter(kind="admin.plan_changed").exists()

    def test_a_refused_change_leaves_no_entry(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        edit(client, plan_id, max_projects=None)  # refused: the plan is active
        assert not AuditEvent.objects.filter(kind="admin.plan_changed").exists()

    def test_deleting_without_a_reason_is_refused(self, boss):
        client, _ = boss
        plan_id = create(client).json()["id"]
        assert client.delete(f"{URL}{plan_id}/", {}, format="json").status_code == 400
        assert Plan.objects.filter(pk=plan_id).exists()


class TestOnlySuperAdminsCanChangePlans:
    def test_support_is_refused_everything_even_when_the_address_is_typed_in(self):
        support, _ = client_for("support")
        plan_id = Plan.objects.first().pk
        before = list(Plan.objects.values())
        for response in (
            support.get(URL),
            support.get(f"{URL}{plan_id}/"),
            create(support),
            edit(support, plan_id, name="Hacked"),
            support.delete(f"{URL}{plan_id}/", {"reason": REASON}, format="json"),
        ):
            assert (response.status_code, response.json()["error"]["code"]) == (403, "not_allowed")
        assert list(Plan.objects.values()) == before
        assert not AuditEvent.objects.filter(kind__startswith="admin.plan").exists()

    def test_visitors_and_company_sign_ins_are_refused(self):
        from core.tests.factories import make_company_user

        assert APIClient().get(URL).status_code == 401
        owner = make_company_user(role="owner")
        issued = signin.start_session(
            user_id=owner.pk, role="owner", company_id=owner.company_id, kind="company"
        )
        company = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert company.get(URL).status_code == 401
        assert create(company).status_code == 401

    def test_a_demoted_admin_loses_the_right_at_once(self, boss):
        client, admin = boss
        make_admin_user(role="super")  # another super admin stays
        assert client.get(URL).status_code == 200
        from adminusers.admin_accounts import change_role

        change_role(admin.pk, "support", by=admin, reason=REASON)
        assert client.get(URL).status_code == 403
