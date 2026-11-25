from datetime import timedelta
from unittest.mock import patch

import pytest
import stripe
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.errors import AppError
from core.tests.factories import make_company, make_company_user
from plans import stripe_client
from plans import subscriptions as subs
from plans.models import Subscription
from plans.tests.test_payment_notifications import SECRET, event_of, paid, send
from plans.tests.test_plan_change import client_of, plan_of
from plans.tests.test_renewal import CUSTOMER, SUB, TEST_KEY, payment_failed_event

pytestmark = pytest.mark.django_db
OPEN = "/api/company/billing/card/update/"
CHECK = "/api/company/billing/card/check/"
CARD = "/api/company/billing/card/"
State = Subscription.State
OLD = {
    "payment_method_id": "pm_test_old",
    "brand": "visa",
    "last4": "4242",
    "exp_month": 4,
    "exp_year": 2030,
}
NEW = {**OLD, "payment_method_id": "pm_test_new", "brand": "mastercard", "last4": "4444"}


class FakeProvider:
    """Stands in for the payment provider: the default card it reports, and what it was asked."""

    def __init__(self):
        self.card = OLD
        self.unreadable = False
        self.portals = []
        self.retries = []
        self.reads = 0

    def portal(self, *, customer_id, return_url, flow=None):
        self.portals.append({"customer_id": customer_id, "return_url": return_url, "flow": flow})
        return "https://billing.example.test/card"

    def default_card(self, customer_id, subscription_id=""):
        self.reads += 1
        if self.unreadable:
            raise AppError("payment_provider_error", "Plain.", status_code=502)
        return self.card

    def retry(self, subscription_id):
        self.retries.append(subscription_id)
        return True


@pytest.fixture
def provider():
    fake = FakeProvider()
    with (
        patch.object(stripe_client, "create_portal_session", fake.portal),
        patch.object(stripe_client, "default_card", fake.default_card),
        patch.object(stripe_client, "retry_open_invoice", fake.retry),
    ):
        yield fake


@pytest.fixture(autouse=True)
def webhook_secret():
    with override_settings(STRIPE_WEBHOOK_SECRET=SECRET):
        yield


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner_user(company):
    return make_company_user(company, role="owner")


@pytest.fixture
def owner(owner_user):
    return client_of(owner_user)


@pytest.fixture
def plan():
    return plan_of("Fake Plan", "10.00")


@pytest.fixture
def now():
    return timezone.now()


@pytest.fixture
def running(company, owner_user, plan, now):
    subs.activate(
        company.pk,
        plan,
        period_start=now - timedelta(days=10),
        period_end=now + timedelta(days=20),
        stripe_customer_id=CUSTOMER,
        stripe_subscription_id=SUB,
    )
    return company


def current(company):
    return Subscription.objects.get(company=company)


def make_past_due(company, plan, now):
    send(payment_failed_event(company, plan, created=now))
    assert current(company).state == State.PAST_DUE


class TestOpening:
    def test_the_owner_gets_the_card_screen_of_the_providers_page(self, running, owner, provider):
        assert owner.post(OPEN).json() == {"url": "https://billing.example.test/card"}
        assert provider.portals[0]["flow"] == {"type": "payment_method_update"}

    def test_it_is_the_companys_own_customer_and_nothing_from_the_request(
        self, running, owner, provider
    ):
        owner.post(OPEN, {"customer_id": "cus_somebody_else"}, format="json")
        assert provider.portals[0]["customer_id"] == CUSTOMER

    def test_the_return_address_is_fixed_and_carries_only_a_marker(self, running, owner, provider):
        owner.post(OPEN, {"return_url": "https://evil.example.test"}, format="json")
        with override_settings(WEB_BASE_URL="https://app.example.test"):
            owner.post(OPEN)
        assert provider.portals[0]["return_url"].endswith("/company/billing?card=returned")
        assert "evil" not in provider.portals[0]["return_url"]
        assert provider.portals[1]["return_url"] == (
            "https://app.example.test/company/billing?card=returned"
        )

    @pytest.mark.parametrize("state", ["past_due", "cancelled", "expired"])
    def test_it_opens_in_every_state_that_has_a_customer(self, running, owner, provider, state):
        Subscription.objects.filter(company=running).update(
            state=state, past_due_since=timezone.now()
        )
        assert owner.post(OPEN).status_code == 200

    def test_a_company_that_never_paid_by_card_has_no_card_page(self, company, owner, provider):
        reply = owner.post(OPEN)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "no_billing_account")
        assert provider.portals == [] and provider.reads == 0

    def test_only_the_owner_may_open_it(self, running, provider):
        member = client_of(make_company_user(running, role="member"))
        assert member.post(OPEN).status_code == 403
        assert provider.portals == []

    def test_a_visitor_may_not(self, provider):
        assert APIClient().post(OPEN).status_code in (401, 403)

    def test_opening_it_is_a_security_event_with_no_card_details(self, running, owner, provider):
        owner.post(OPEN)
        entry = AuditEvent.objects.get(kind="security.card_update_opened")
        assert (entry.actor_kind, entry.company_id) == ("company", running.pk)
        assert entry.details == {"state": "active"}

    def test_the_card_that_was_the_default_is_remembered_by_its_id(self, running, owner, provider):
        owner.post(OPEN)
        after = current(running)
        assert after.card_update_started_with == "pm_test_old"
        assert after.card_update_started_at is not None and after.card_update_outcome == ""

    def test_a_company_with_no_card_yet_remembers_none(self, running, owner, provider):
        provider.card = None
        owner.post(OPEN)
        assert current(running).card_update_started_with == ""

    def test_a_provider_failure_gives_one_plain_sentence_and_records_nothing(
        self, running, owner, provider
    ):
        def fail(**sent):
            raise AppError("payment_provider_error", "Plain.", status_code=502)

        with patch.object(stripe_client, "create_portal_session", fail):
            assert owner.post(OPEN).status_code == 502
        assert current(running).card_update_started_at is None
        assert not AuditEvent.objects.filter(kind="security.card_update_opened").exists()

    def test_opening_again_starts_a_new_visit(self, running, owner, provider):
        owner.post(OPEN)
        owner.post(CHECK)
        owner.post(OPEN)
        assert current(running).card_update_outcome == ""


class TestResult:
    def test_before_any_visit_there_is_nothing_to_report(self, running, owner, provider):
        assert owner.post(CHECK).json() == {"result": "none"}
        assert provider.reads == 0

    def test_a_changed_default_card_is_updated(self, running, owner, provider):
        owner.post(OPEN)
        provider.card = NEW
        assert owner.post(CHECK).json() == {"result": "updated"}

    def test_the_first_card_ever_added_is_updated(self, running, owner, provider):
        provider.card = None
        owner.post(OPEN)
        provider.card = NEW
        assert owner.post(CHECK).json() == {"result": "updated"}

    def test_the_same_card_is_not_changed(self, running, owner, provider):
        owner.post(OPEN)
        assert owner.post(CHECK).json() == {"result": "not_changed"}

    def test_a_result_in_the_request_is_never_believed(self, running, owner, provider):
        owner.post(OPEN)
        reply = owner.post(CHECK, {"result": "updated", "card": "updated"}, format="json")
        assert reply.json() == {"result": "not_changed"}

    def test_when_the_provider_cannot_be_read_it_says_checking_and_saves_nothing(
        self, running, owner, provider
    ):
        owner.post(OPEN)
        provider.unreadable = True
        assert owner.post(CHECK).json() == {"result": "checking"}
        assert current(running).card_update_outcome == ""
        assert not AuditEvent.objects.filter(kind="security.card_update_result").exists()
        provider.unreadable = False
        provider.card = NEW
        assert owner.post(CHECK).json() == {"result": "updated"}

    def test_the_providers_notice_tells_it_when_the_provider_cannot_be_read(
        self, running, owner, provider
    ):
        owner.post(OPEN)
        provider.unreadable = True
        send(event_of("payment_method.attached", {"id": "pm_x", "customer": CUSTOMER},
                      created=timezone.now() + timedelta(minutes=1)))  # fmt: skip
        assert owner.post(CHECK).json() == {"result": "updated"}

    def test_a_notice_from_before_the_visit_says_nothing(self, running, owner, provider):
        owner.post(OPEN)
        send(event_of("payment_method.attached", {"id": "pm_x", "customer": CUSTOMER},
                      created=timezone.now() - timedelta(hours=1)))  # fmt: skip
        provider.unreadable = True
        assert owner.post(CHECK).json() == {"result": "checking"}

    def test_a_notice_for_another_customer_changes_nothing(self, running, owner, provider):
        owner.post(OPEN)
        send(event_of("payment_method.attached", {"id": "pm_x", "customer": "cus_other"},
                      created=timezone.now() + timedelta(minutes=1)))  # fmt: skip
        provider.unreadable = True
        assert owner.post(CHECK).json() == {"result": "checking"}

    def test_a_notice_without_a_customer_is_acknowledged_and_ignored(self, running, provider):
        reply = send(event_of("payment_method.attached", {"id": "pm_x"}))
        assert reply.status_code == 200

    def test_the_result_is_a_security_event_once_with_no_card_details(
        self, running, owner, provider
    ):
        owner.post(OPEN)
        provider.card = NEW
        owner.post(CHECK), owner.post(CHECK)
        entry = AuditEvent.objects.get(kind="security.card_update_result")
        assert entry.details == {"result": "updated"}
        assert "4444" not in str(entry.details) and "pm_test" not in str(entry.details)

    def test_asking_again_gives_the_saved_result_without_asking_the_provider(
        self, running, owner, provider
    ):
        owner.post(OPEN)
        owner.post(CHECK)
        reads = provider.reads
        provider.card = NEW
        assert owner.post(CHECK).json() == {"result": "not_changed"}
        assert provider.reads == reads

    def test_only_the_owner_may_ask(self, running, provider):
        member = client_of(make_company_user(running, role="member"))
        assert member.post(CHECK).status_code == 403


class TestPastDue:
    def test_a_new_card_asks_the_provider_to_pay_the_open_invoice_again_once(
        self, running, plan, owner, provider, now
    ):
        make_past_due(running, plan, now)
        owner.post(OPEN)
        provider.card = NEW
        owner.post(CHECK), owner.post(CHECK)
        assert provider.retries == [SUB]

    def test_access_does_not_come_back_by_itself(self, running, plan, owner, provider, now):
        make_past_due(running, plan, now)
        owner.post(OPEN)
        provider.card = NEW
        owner.post(CHECK)
        assert owner.get("/api/company/usage/").json()["state"] == "past_due"

    def test_only_the_paid_notice_restores_it(self, running, plan, owner, provider, now):
        make_past_due(running, plan, now)
        owner.post(OPEN)
        provider.card = NEW
        owner.post(CHECK)
        later = now + timedelta(hours=1)
        send(paid(running, plan, start=later, end=later + timedelta(days=30), created=later))
        assert owner.get("/api/company/usage/").json()["state"] == "active"

    def test_the_same_card_pays_nothing_again(self, running, plan, owner, provider, now):
        make_past_due(running, plan, now)
        owner.post(OPEN)
        owner.post(CHECK)
        assert provider.retries == []

    def test_a_company_that_is_not_past_due_asks_for_no_payment(self, running, owner, provider):
        owner.post(OPEN)
        provider.card = NEW
        owner.post(CHECK)
        assert provider.retries == []

    def test_a_past_due_company_can_open_it_and_see_its_card(
        self, running, plan, owner, provider, now
    ):
        make_past_due(running, plan, now)
        assert owner.post(OPEN).status_code == 200
        assert owner.get(CARD).status_code == 200


class TestShowingTheCard:
    def test_the_owner_sees_brand_last_four_and_expiry_only(self, running, owner, provider):
        reply = owner.get(CARD)
        assert reply.json() == {
            "card": {"brand": "visa", "last4": "4242", "exp_month": 4, "exp_year": 2030}
        }
        assert reply["Cache-Control"] == "no-store"

    def test_no_card_is_shown_as_none(self, running, owner, provider):
        provider.card = None
        assert owner.get(CARD).json() == {"card": None}

    def test_a_member_may_not_see_it(self, running, provider):
        member = client_of(make_company_user(running, role="member"))
        assert member.get(CARD).status_code == 403
        assert provider.reads == 0

    def test_a_company_without_a_customer_has_none(self, company, owner, provider):
        assert owner.get(CARD).status_code == 409

    def test_a_visitor_may_not(self, provider):
        assert APIClient().get(CARD).status_code in (401, 403)

    def test_nothing_about_the_card_is_stored_here(self):
        stored = {field.name for field in Subscription._meta.get_fields()}
        assert not {"last4", "brand", "card_number", "exp_month", "exp_year"} & stored


class TestTheProviderClient:
    def test_the_portal_opens_on_the_card_screen_only_when_asked(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.billing_portal.Session, "create", return_value={"url": "https://x.test/p"}
            ) as create,
        ):
            stripe_client.create_portal_session(
                customer_id=CUSTOMER,
                return_url="https://app.example.test/back",
                flow=stripe_client.CARD_UPDATE_FLOW,
            )
        assert create.call_args.kwargs["flow_data"] == {"type": "payment_method_update"}

    def test_the_subscriptions_own_card_wins(self):
        method = {"id": "pm_1", "card": {"brand": "visa", "last4": "4242", "exp_month": 1,
                                         "exp_year": 2031}}  # fmt: skip
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Subscription, "retrieve", return_value={"default_payment_method": method}
            ),
            patch.object(stripe.Customer, "retrieve") as customer,
        ):
            card = stripe_client.default_card(CUSTOMER, SUB)
        assert card == {
            "payment_method_id": "pm_1",
            "brand": "visa",
            "last4": "4242",
            "exp_month": 1,
            "exp_year": 2031,
        }
        customer.assert_not_called()

    def test_the_customers_card_is_used_when_the_subscription_has_none(self):
        method = {"id": "pm_2", "card": {"brand": "visa", "last4": "1111", "exp_month": 2,
                                         "exp_year": 2032}}  # fmt: skip
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Subscription, "retrieve", return_value={"default_payment_method": None}
            ),
            patch.object(
                stripe.Customer,
                "retrieve",
                return_value={"invoice_settings": {"default_payment_method": method}},
            ),
        ):
            assert stripe_client.default_card(CUSTOMER, SUB)["payment_method_id"] == "pm_2"

    def test_no_card_at_all_is_none(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Customer,
                "retrieve",
                return_value={"invoice_settings": {"default_payment_method": None}},
            ),
        ):
            assert stripe_client.default_card(CUSTOMER) is None

    def test_a_provider_error_becomes_the_plain_message(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(stripe.Customer, "retrieve", side_effect=stripe.APIConnectionError("hid")),
            pytest.raises(AppError) as caught,
        ):
            stripe_client.default_card(CUSTOMER)
        assert "hid" not in caught.value.message

    def test_a_key_that_is_not_a_test_key_is_refused(self):
        with override_settings(STRIPE_SECRET_KEY="sk_live_x"):  # nosecret: fake
            with pytest.raises(AppError) as caught:
                stripe_client.default_card(CUSTOMER)
        assert caught.value.code == stripe_client.UNAVAILABLE_CODE

    def test_an_open_invoice_is_paid_again(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Subscription,
                "retrieve",
                return_value={"latest_invoice": {"id": "in_1", "status": "open"}},
            ),
            patch.object(stripe.Invoice, "pay") as pay,
        ):
            assert stripe_client.retry_open_invoice(SUB) is True
        assert pay.call_args.args == ("in_1",)

    def test_an_invoice_that_is_not_open_is_left_alone(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Subscription,
                "retrieve",
                return_value={"latest_invoice": {"id": "in_1", "status": "paid"}},
            ),
            patch.object(stripe.Invoice, "pay") as pay,
        ):
            assert stripe_client.retry_open_invoice(SUB) is False
        pay.assert_not_called()

    def test_a_declined_card_or_an_outage_is_reported_not_raised(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Subscription,
                "retrieve",
                return_value={"latest_invoice": {"id": "in_1", "status": "open"}},
            ),
            patch.object(stripe.Invoice, "pay", side_effect=stripe.CardError("no", "p", "c")),
        ):
            assert stripe_client.retry_open_invoice(SUB) is False
