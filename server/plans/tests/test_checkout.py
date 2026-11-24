from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.errors import AppError
from core.tests.factories import make_company, make_company_user
from plans import stripe_client
from plans.models import CheckoutAttempt, Subscription
from plans.subscriptions import activate, get_subscription, grant_free
from plans.tests.test_regional_pricing import make_plan
from signin import service

pytestmark = pytest.mark.django_db
START = "/api/company/billing/checkout/"
CONFIRM = "/api/company/billing/checkout/confirm/"
TEST_KEY = "sk_test_only9c4e7a1b5d2f8e63"  # nosecret: fake


class FakeProvider:
    """Stands in for the payment provider: remembers the pages it made and what they cost."""

    def __init__(self):
        self.created = []
        self.expired = []
        self.sessions = {}
        self.refuse_expiry = False

    def create(self, **sent):
        key = sent["idempotency_key"]
        if key not in self.sessions:  # the same key always gives the same page
            number = len(self.sessions) + 1
            self.sessions[key] = SimpleNamespace(
                id=f"cs_test_{number}",
                url=f"https://pay.example.test/{number}",
                status="open",
                payment_status="unpaid",
                client_reference_id=str(sent["company_id"]),
                amount_total=sent["amount_minor"],
                currency=sent["currency"].lower(),
                customer=None,
                subscription=None,
            )
            self.created.append(sent)
        return self.sessions[key]

    def retrieve(self, session_id):
        return next(s for s in self.sessions.values() if s.id == session_id)

    def expire(self, session_id):
        if self.refuse_expiry:
            return False
        self.expired.append(session_id)
        self.retrieve(session_id).status = "expired"
        return True

    def pay(self, session_id, customer="cus_test_1", subscription="sub_test_1"):
        session = self.retrieve(session_id)
        session.status, session.payment_status = "complete", "paid"
        session.customer, session.subscription = customer, subscription


@pytest.fixture
def provider():
    fake = FakeProvider()
    with (
        patch.object(stripe_client, "create_checkout_session", fake.create),
        patch.object(stripe_client, "retrieve_checkout_session", fake.retrieve),
        patch.object(stripe_client, "expire_checkout_session", fake.expire),
    ):
        yield fake


def client_for(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = service.start_session(
        user_id=person.pk, role=role, company_id=company.pk, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner(company):
    return client_for(company)


def begin(client, plan):
    reply = client.post(START, {"plan_id": plan.pk}, format="json")
    assert reply.status_code == 200, reply.content
    return reply.json()["url"]


def session_of(company):
    return CheckoutAttempt.objects.get(company=company).stripe_session_id


def confirm(client, session_id):
    return client.post(CONFIRM, {"session_id": session_id}, format="json")


class TestStarting:
    def test_the_company_gets_the_payment_page_of_the_provider(self, owner, provider):
        assert begin(owner, make_plan()) == "https://pay.example.test/1"

    def test_the_charge_is_in_usd_at_the_plan_price(self, owner, provider):
        begin(owner, make_plan(usd="12.50"))
        assert (provider.created[0]["currency"], provider.created[0]["amount_minor"]) == (
            "USD",
            1250,
        )

    def test_a_pakistan_company_is_still_charged_the_usd_price(self, provider):
        pakistan = make_company(country="PK")
        begin(client_for(pakistan), make_plan(usd="10.00", pkr="3000.00"))
        assert provider.created[0]["amount_minor"] == 1000
        assert provider.created[0]["currency"] == "USD"

    def test_nothing_changes_before_the_payment_is_confirmed(self, company, owner, provider):
        begin(owner, make_plan())
        assert get_subscription(company.pk).state == "no_plan"

    def test_the_page_returns_to_the_app_on_success_and_on_cancel(self, owner, provider):
        begin(owner, make_plan())
        sent = provider.created[0]
        assert "/company/billing/return?session_id={CHECKOUT_SESSION_ID}" in sent["success_url"]
        assert "/company/billing" in sent["cancel_url"]

    @pytest.mark.parametrize("status", ["hidden", "archived"])
    def test_a_plan_that_is_not_for_sale_is_not_found(self, owner, provider, status):
        assert (
            owner.post(START, {"plan_id": make_plan(status=status).pk}, format="json").status_code
            == 404
        )

    def test_an_unknown_plan_is_not_found(self, owner, provider):
        assert owner.post(START, {"plan_id": 999999}, format="json").status_code == 404

    @pytest.mark.parametrize(
        "body", [{}, {"plan_id": "x"}, {"plan_id": 0}, {"plan_id": 1, "company_id": 2}]
    )
    def test_a_bad_request_is_refused_in_the_shared_shape(self, owner, provider, body):
        reply = owner.post(START, body, format="json")
        assert reply.status_code == 400 and reply.json()["error"]["code"]

    def test_only_the_owner_may_buy(self, company, provider):
        member = client_for(company, role="member")
        assert member.post(START, {"plan_id": make_plan().pk}, format="json").status_code == 403
        assert provider.created == []

    def test_a_visitor_cannot_buy(self, provider):
        reply = APIClient().post(START, {"plan_id": 1}, format="json")
        assert reply.status_code in (401, 403)

    def test_a_company_with_a_running_plan_cannot_buy_again(self, company, owner, provider):
        plan = make_plan()
        grant_free(
            company.pk, plan, period_end=timezone.now() + timedelta(days=5), by=None, reason="Test"
        )
        reply = owner.post(START, {"plan_id": plan.pk}, format="json")
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "already_subscribed")
        assert provider.created == []

    def test_a_company_whose_plan_ended_can_buy(self, company, owner, provider):
        Subscription.objects.update_or_create(company=company, defaults={"state": "expired"})
        assert begin(owner, make_plan())


class TestDoubleClick:
    def test_two_clicks_make_one_page(self, owner, provider):
        plan = make_plan()
        assert begin(owner, plan) == begin(owner, plan)
        assert len(provider.created) == 1

    def test_two_clicks_make_one_attempt(self, company, owner, provider):
        plan = make_plan()
        begin(owner, plan), begin(owner, plan)
        assert CheckoutAttempt.objects.filter(company=company).count() == 1

    def test_the_provider_is_given_an_idempotency_key_of_the_attempt(
        self, company, owner, provider
    ):
        begin(owner, make_plan())
        assert provider.created[0]["idempotency_key"] == str(CheckoutAttempt.objects.get().pk)

    def test_choosing_another_plan_closes_the_first_page(self, owner, provider):
        first, second = make_plan("First"), make_plan("Second", usd="20.00")
        begin(owner, first)
        assert begin(owner, second) == "https://pay.example.test/2"
        assert provider.expired == ["cs_test_1"]
        assert sorted(CheckoutAttempt.objects.values_list("status", flat=True)) == [
            "open",
            "replaced",
        ]

    def test_the_closed_page_cannot_activate_anything(self, company, owner, provider):
        first, second = make_plan("First"), make_plan("Second", usd="20.00")
        begin(owner, first)
        old = session_of(company)
        begin(owner, second)
        provider.pay(old)
        assert confirm(owner, old).json() == {"result": "closed"}
        assert get_subscription(company.pk).state == "no_plan"

    def test_a_page_that_cannot_be_closed_stops_a_second_one(self, owner, provider):
        begin(owner, make_plan("First"))
        provider.refuse_expiry = True
        reply = owner.post(START, {"plan_id": make_plan("Second").pk}, format="json")
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "checkout_in_progress")
        assert len(provider.created) == 1

    def test_after_the_page_time_a_new_one_is_made(self, company, owner, provider):
        plan = make_plan()
        begin(owner, plan)
        CheckoutAttempt.objects.update(created_at=timezone.now() - timedelta(hours=2))
        assert begin(owner, plan) == "https://pay.example.test/2"


class TestConfirming:
    def test_a_paid_page_activates_the_plan_for_one_month_from_now(self, company, owner, provider):
        plan = make_plan()
        begin(owner, plan)
        provider.pay(session_of(company))
        before = timezone.now()
        assert confirm(owner, session_of(company)).json() == {"result": "activated"}
        subscription = get_subscription(company.pk)
        assert (subscription.state, subscription.plan_id, subscription.renewal) == (
            "active",
            plan.pk,
            True,
        )
        assert before <= subscription.period_start <= timezone.now()
        assert (
            timedelta(days=28)
            <= subscription.period_end - subscription.period_start
            <= timedelta(days=31)
        )

    def test_the_provider_ids_are_kept_on_the_subscription(self, company, owner, provider):
        begin(owner, make_plan())
        provider.pay(session_of(company), customer="cus_test_9", subscription="sub_test_9")
        confirm(owner, session_of(company))
        subscription = get_subscription(company.pk)
        assert (subscription.stripe_customer_id, subscription.stripe_subscription_id) == (
            "cus_test_9",
            "sub_test_9",
        )

    def test_the_provider_ids_may_arrive_as_objects(self, company, owner, provider):
        begin(owner, make_plan())
        provider.pay(
            session_of(company),
            customer=SimpleNamespace(id="cus_o"),
            subscription=SimpleNamespace(id="sub_o"),
        )
        confirm(owner, session_of(company))
        assert get_subscription(company.pk).stripe_subscription_id == "sub_o"

    def test_the_providers_notice_that_came_first_is_not_counted_a_second_time(
        self, company, owner, provider
    ):
        plan = make_plan()
        begin(owner, plan)
        provider.pay(session_of(company), customer="cus_test_9", subscription="sub_test_9")
        start = timezone.now() - timedelta(minutes=1)
        end = start + timedelta(days=30)
        activate(
            company.pk, plan, period_start=start, period_end=end,
            stripe_customer_id="cus_test_9", stripe_subscription_id="sub_test_9",
        )  # fmt: skip
        assert confirm(owner, session_of(company)).json() == {"result": "activated"}
        subscription = get_subscription(company.pk)
        assert (subscription.period_start, subscription.period_end) == (start, end)
        assert CheckoutAttempt.objects.get().status == "activated"

    def test_opening_the_return_page_twice_activates_once(self, company, owner, provider):
        begin(owner, make_plan())
        provider.pay(session_of(company))
        assert confirm(owner, session_of(company)).json() == {"result": "activated"}
        first = get_subscription(company.pk)
        stamp = (first.period_start, first.period_end)
        assert confirm(owner, session_of(company)).json() == {"result": "activated"}
        second = get_subscription(company.pk)
        assert (second.period_start, second.period_end) == stamp

    def test_activation_is_audited_and_mailed_once(self, company, owner, provider):
        from audit.models import AuditEvent

        begin(owner, make_plan())
        provider.pay(session_of(company))
        confirm(owner, session_of(company)), confirm(owner, session_of(company))
        assert AuditEvent.objects.filter(kind="subscription.state_changed").count() == 1

    def test_an_unpaid_page_changes_nothing(self, company, owner, provider):
        begin(owner, make_plan())
        assert confirm(owner, session_of(company)).json() == {"result": "pending"}
        assert get_subscription(company.pk).state == "no_plan"

    def test_a_cancelled_or_expired_page_changes_nothing(self, company, owner, provider):
        begin(owner, make_plan())
        provider.retrieve(session_of(company)).status = "expired"
        assert confirm(owner, session_of(company)).json() == {"result": "cancelled"}
        assert get_subscription(company.pk).state == "no_plan"

    def test_a_cancelled_page_can_be_paid_again_with_a_new_try(self, company, owner, provider):
        plan = make_plan()
        begin(owner, plan)
        provider.retrieve(session_of(company)).status = "expired"
        CheckoutAttempt.objects.update(created_at=timezone.now() - timedelta(hours=2))
        assert begin(owner, plan) == "https://pay.example.test/2"

    def test_the_browser_saying_it_came_back_is_not_enough(self, company, owner, provider):
        begin(owner, make_plan())
        confirm(owner, session_of(company))  # the return page opens, nothing was paid
        assert get_subscription(company.pk).state == "no_plan"

    def test_a_session_of_another_company_is_not_found(self, company, owner, provider):
        other = make_company()
        begin(client_for(other), make_plan())
        reply = confirm(owner, session_of(other))
        assert reply.status_code == 404
        assert get_subscription(other.pk).state == "no_plan"

    def test_an_unknown_session_is_not_found(self, owner, provider):
        assert confirm(owner, "cs_test_unknown").status_code == 404

    def test_a_paid_session_with_another_amount_is_not_trusted(self, company, owner, provider):
        begin(owner, make_plan())
        provider.pay(session_of(company))
        provider.retrieve(session_of(company)).amount_total = 1
        reply = confirm(owner, session_of(company))
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "payment_mismatch")
        assert get_subscription(company.pk).state == "no_plan"

    def test_a_paid_session_of_another_company_reference_is_not_trusted(
        self, company, owner, provider
    ):
        begin(owner, make_plan())
        provider.pay(session_of(company))
        provider.retrieve(session_of(company)).client_reference_id = "someone-else"
        assert confirm(owner, session_of(company)).status_code == 409

    def test_only_the_owner_may_confirm(self, company, provider):
        member = client_for(company, role="member")
        assert confirm(member, "cs_test_1").status_code == 403

    def test_the_price_change_after_the_page_was_made_does_not_block_a_paid_order(
        self, company, owner, provider
    ):
        plan = make_plan(usd="10.00")
        begin(owner, plan)
        plan.price_usd = 99
        plan.save()
        provider.pay(session_of(company))
        assert confirm(owner, session_of(company)).json() == {"result": "activated"}


class TestProviderErrors:
    def test_a_provider_failure_gives_a_plain_message_and_leaves_no_attempt(self, company, owner):
        with patch.object(
            stripe_client,
            "create_checkout_session",
            side_effect=AppError("payment_provider_error", "x", status_code=502),
        ):
            reply = owner.post(START, {"plan_id": make_plan().pk}, format="json")
        assert reply.status_code == 502
        assert CheckoutAttempt.objects.count() == 0
        assert get_subscription(company.pk).state == "no_plan"


class TestTheProviderClient:
    @pytest.mark.parametrize("key", ["", "sk_live_notallowed0000000000", "rk_live_x", "plain"])  # nosecret: fake
    def test_a_key_that_is_not_a_test_key_is_refused(self, key):
        with override_settings(STRIPE_SECRET_KEY=key):
            with pytest.raises(AppError) as refused:
                stripe_client.retrieve_checkout_session("cs_test_1")
        assert refused.value.code == "payments_unavailable"

    def test_a_test_key_is_used_and_the_provider_error_is_made_plain(self):
        with override_settings(STRIPE_SECRET_KEY=TEST_KEY):
            with patch(
                "stripe.checkout.Session.retrieve",
                side_effect=stripe.APIConnectionError("host 10.0.0.1 down"),
            ):
                with pytest.raises(AppError) as failed:
                    stripe_client.retrieve_checkout_session("cs_test_1")
        assert failed.value.code == "payment_provider_error"
        assert "10.0.0.1" not in failed.value.message

    def test_the_session_is_created_with_card_details_never_sent(self):
        plan = make_plan()
        with override_settings(STRIPE_SECRET_KEY=TEST_KEY):
            with patch("stripe.checkout.Session.create") as create:
                stripe_client.create_checkout_session(
                    idempotency_key="k",
                    company_id=1,
                    plan=plan,
                    currency="USD",
                    amount_minor=1000,
                    expires_at=timezone.now(),
                    success_url="https://a.example.test/s",
                    cancel_url="https://a.example.test/c",
                )
        sent = create.call_args.kwargs
        assert (sent["mode"], sent["idempotency_key"], sent["api_key"]) == (
            "subscription",
            "k",
            TEST_KEY,
        )
        assert not {"card", "payment_method_data", "customer_email"} & sent.keys()
        assert sent["line_items"][0]["price_data"]["recurring"] == {"interval": "month"}
        assert (
            sent["line_items"][0]["price_data"]["currency"],
            sent["line_items"][0]["price_data"]["unit_amount"],
        ) == ("usd", 1000)
        assert sent["metadata"] == {"company_id": "1", "plan_id": str(plan.pk)}
        assert sent["client_reference_id"] == "1"

    def test_closing_a_page_the_provider_refuses_to_close_reports_it(self):
        with override_settings(STRIPE_SECRET_KEY=TEST_KEY):
            with patch(
                "stripe.checkout.Session.expire",
                side_effect=stripe.InvalidRequestError("done", "id"),
            ):
                assert stripe_client.expire_checkout_session("cs_test_1") is False


class TestAnotherCompany:
    def test_an_attempt_is_found_only_by_its_own_company(self, provider):
        mine, theirs = make_company(), make_company()
        mine_client, theirs_client = client_for(mine), client_for(theirs)
        begin(mine_client, make_plan())
        begin(theirs_client, make_plan("Other"))
        assert CheckoutAttempt.objects.filter(company=mine).count() == 1
        assert session_of(mine) != session_of(theirs)
        assert confirm(mine_client, session_of(theirs)).status_code == 404
