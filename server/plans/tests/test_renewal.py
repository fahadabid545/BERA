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
from cvs.tests.test_processing import set_setting
from emailing.models import OutgoingEmail
from notifications.billing_notices import send_renewal_notices
from plans import stripe_client
from plans import subscriptions as subs
from plans.models import Subscription
from plans.tests.test_payment_notifications import SECRET, event_of, failed, send, stamp
from plans.tests.test_plan_change import client_of, plan_of

pytestmark = pytest.mark.django_db
CANCEL = "/api/company/billing/cancel/"
RESUME = "/api/company/billing/resume/"
PORTAL = "/api/company/billing/portal/"
SUB = "sub_test_1"
CUSTOMER = "cus_test_1"
TEST_KEY = "sk_test_only9c4e7a1b5d2f8e63"  # nosecret: fake
State = Subscription.State


class FakeProvider:
    """Stands in for the payment provider and remembers what it was asked."""

    def __init__(self):
        self.renewal_calls = []
        self.ended = []
        self.portals = []
        self.already_ended = False

    def set_renewal(self, subscription_id, stops):
        self.renewal_calls.append((subscription_id, stops))
        return not self.already_ended

    def end(self, subscription_id):
        self.ended.append(subscription_id)
        return True

    def portal(self, *, customer_id, return_url, flow=None):
        self.portals.append({"customer_id": customer_id, "return_url": return_url, "flow": flow})
        return "https://billing.example.test/session"


@pytest.fixture
def provider():
    fake = FakeProvider()
    with (
        patch.object(stripe_client, "set_renewal_stops_at_period_end", fake.set_renewal),
        patch.object(stripe_client, "end_subscription", fake.end),
        patch.object(stripe_client, "create_portal_session", fake.portal),
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


def subscribe(company, plan, now, *, ends_in=20):
    subs.activate(
        company.pk,
        plan,
        period_start=now - timedelta(days=30 - ends_in),
        period_end=now + timedelta(days=ends_in),
        stripe_customer_id=CUSTOMER,
        stripe_subscription_id=SUB,
    )


@pytest.fixture
def running(company, owner_user, plan, now):
    subscribe(company, plan, now)
    return company


def current(company):
    return Subscription.objects.get(company=company)


def mails(template):
    return [mail for mail in OutgoingEmail.objects.all() if mail.template == template]


def payment_failed_event(company, plan, *, created):
    event = failed(company, plan, start=created, end=created + timedelta(days=30), created=created)
    return event


class TestCancel:
    def test_the_provider_stops_the_renewal_and_the_subscription_is_cancelled(
        self, running, owner, provider
    ):
        assert owner.post(CANCEL).json() == {"result": "cancelled"}
        assert provider.renewal_calls == [(SUB, True)]
        after = current(running)
        assert (after.state, after.renewal) == (State.CANCELLED, False)

    def test_full_access_continues_until_the_period_ends(self, running, owner, provider):
        before = current(running).period_end
        owner.post(CANCEL)
        assert current(running).period_end == before
        assert subs.can_upload(running.pk) and subs.can_score(running.pk)
        assert subs.effective_state(current(running)) == State.CANCELLED

    def test_after_the_period_the_account_is_view_and_download_only(self, running, owner, provider):
        owner.post(CANCEL)
        Subscription.objects.filter(company=running).update(
            period_end=timezone.now() - timedelta(minutes=1)
        )
        assert subs.effective_state(current(running)) == State.EXPIRED
        assert subs.can_view(running.pk)
        assert not subs.can_upload(running.pk)
        assert not subs.can_create_project(running.pk)
        assert not subs.can_score(running.pk)

    def test_the_owner_is_told_and_it_is_audited(self, running, owner, provider):
        owner.post(CANCEL)
        assert len(mails("usage_notice")) == 2  # activation, then the cancellation
        entry = AuditEvent.objects.filter(kind="subscription.state_changed").latest("id")
        assert entry.details["changes"]["state"] == {"old": "active", "new": "cancelled"}

    def test_a_waiting_downgrade_is_dropped_with_it(self, running, owner, provider, plan):
        smaller = plan_of("Fake Smaller", "5.00")
        Subscription.objects.filter(company=running).update(
            pending_plan=smaller, pending_change="downgrade", pending_since=timezone.now()
        )
        owner.post(CANCEL)
        assert current(running).pending_plan is None

    def test_a_second_click_changes_nothing_more(self, running, owner, provider):
        owner.post(CANCEL)
        reply = owner.post(CANCEL)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "cancel_unavailable")
        assert provider.renewal_calls == [(SUB, True)]

    def test_a_failure_at_the_provider_changes_nothing(self, running, owner):
        def fail(subscription_id, stops):
            raise AppError("payment_provider_error", "Plain.", status_code=502)

        with patch.object(stripe_client, "set_renewal_stops_at_period_end", fail):
            assert owner.post(CANCEL).status_code == 502
        assert current(running).state == State.ACTIVE and current(running).renewal

    @pytest.mark.parametrize("state", ["past_due", "expired"])
    def test_only_a_running_subscription_can_be_cancelled(self, running, owner, provider, state):
        Subscription.objects.filter(company=running).update(
            state=state, past_due_since=timezone.now()
        )
        assert owner.post(CANCEL).json()["error"]["code"] == "cancel_unavailable"
        assert provider.renewal_calls == []

    def test_a_company_without_card_billing_cannot_cancel(
        self, company, owner, provider, plan, now
    ):
        subs.grant_free(company.pk, plan, period_end=now + timedelta(days=5), by=None, reason="T")
        assert owner.post(CANCEL).json()["error"]["code"] == "cancel_unavailable"

    def test_only_the_owner_may_cancel(self, running, provider):
        member = client_of(make_company_user(running, role="member"))
        assert member.post(CANCEL).status_code == 403
        assert provider.renewal_calls == []

    def test_a_visitor_may_not(self, provider):
        assert APIClient().post(CANCEL).status_code in (401, 403)

    def test_cancelling_touches_only_the_own_company(self, running, owner, provider, plan, now):
        other = make_company()
        make_company_user(other, role="owner")
        subs.activate(
            other.pk, plan, period_start=now, period_end=now + timedelta(days=9),
            stripe_customer_id="cus_other", stripe_subscription_id="sub_other",
        )  # fmt: skip
        owner.post(CANCEL)
        assert current(other).state == State.ACTIVE
        assert provider.renewal_calls == [(SUB, True)]


class TestResume:
    def test_it_renews_again_with_nothing_charged_now(self, running, owner, provider):
        owner.post(CANCEL)
        assert owner.post(RESUME).json() == {"result": "resumed"}
        assert provider.renewal_calls == [(SUB, True), (SUB, False)]
        after = current(running)
        assert (after.state, after.renewal) == (State.ACTIVE, True)

    def test_the_period_is_untouched(self, running, owner, provider):
        before = current(running).period_end
        owner.post(CANCEL), owner.post(RESUME)
        assert current(running).period_end == before

    def test_a_subscription_the_provider_already_ended_cannot_be_resumed(
        self, running, owner, provider
    ):
        owner.post(CANCEL)
        provider.already_ended = True
        reply = owner.post(RESUME)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "resume_unavailable")
        assert current(running).state == State.CANCELLED

    def test_nothing_to_resume_when_it_is_running(self, running, owner, provider):
        assert owner.post(RESUME).json()["error"]["code"] == "resume_unavailable"
        assert provider.renewal_calls == []

    def test_an_ended_period_cannot_be_resumed(self, running, owner, provider):
        owner.post(CANCEL)
        Subscription.objects.filter(company=running).update(
            period_end=timezone.now() - timedelta(minutes=1)
        )
        assert owner.post(RESUME).json()["error"]["code"] == "resume_unavailable"

    def test_only_the_owner_may_resume(self, running, owner, provider):
        owner.post(CANCEL)
        member = client_of(make_company_user(running, role="member"))
        assert member.post(RESUME).status_code == 403


class TestFailedRenewalAndGrace:
    def test_a_failed_renewal_gives_the_grace_period_with_full_access(self, running, plan, now):
        send(payment_failed_event(running, plan, created=now))
        assert current(running).state == State.PAST_DUE
        assert subs.can_upload(running.pk) and subs.can_score(running.pk)
        assert len(mails("payment_problem")) == 1

    def test_the_grace_period_is_seven_days(self, running, plan, now):
        send(payment_failed_event(running, plan, created=now))
        subscription = current(running)
        assert subs.grace_ends_at(subscription) - subscription.past_due_since == timedelta(days=7)
        after_six = now + timedelta(days=6)
        after_eight = now + timedelta(days=8)
        assert subs.effective_state(subscription, after_six) == State.PAST_DUE
        assert subs.effective_state(subscription, after_eight) == State.EXPIRED

    def test_when_the_grace_ends_the_job_ends_access_and_the_provider_subscription(
        self, running, plan, now, provider
    ):
        send(payment_failed_event(running, plan, created=now))
        Subscription.objects.filter(company=running).update(past_due_since=now - timedelta(days=8))
        assert subs.expire_lapsed_subscriptions() == 1
        assert current(running).state == State.EXPIRED
        assert provider.ended == [SUB]
        assert subs.can_view(running.pk) and not subs.can_upload(running.pk)
        assert subs.expire_lapsed_subscriptions() == 0  # nothing happens twice
        assert provider.ended == [SUB]

    def test_a_paid_notice_in_the_grace_period_restores_normal_state(self, running, plan, now):
        send(payment_failed_event(running, plan, created=now))
        end = current(running).period_end
        paid = event_of(
            "invoice.paid",
            {
                "id": "in_test_renewal", "object": "invoice", "customer": CUSTOMER,
                "subscription": SUB,
                "billing_reason": "subscription_cycle", "amount_paid": 1000,
                "amount_due": 1000, "currency": "usd",
                "lines": {"data": [{"period": {
                    "start": stamp(end), "end": stamp(end + timedelta(days=30))}}]},
            },
            created=now + timedelta(days=1),
        )  # fmt: skip
        send(paid)
        after = current(running)
        assert (after.state, after.past_due_since) == (State.ACTIVE, None)
        assert subs.effective_state(after) == State.ACTIVE


class TestExpiry:
    def test_a_cancelled_subscription_ends_at_the_period_end_and_the_owner_is_told(
        self, running, owner, provider
    ):
        owner.post(CANCEL)
        Subscription.objects.filter(company=running).update(
            period_end=timezone.now() - timedelta(minutes=1)
        )
        assert subs.expire_lapsed_subscriptions() == 1
        assert current(running).state == State.EXPIRED
        assert len(mails("usage_notice")) == 3  # active, cancelled, ended

    def test_a_subscription_with_time_left_is_left_alone(self, running, provider):
        assert subs.expire_lapsed_subscriptions() == 0
        assert provider.ended == []

    def test_a_company_without_a_provider_subscription_asks_the_provider_nothing(
        self, company, owner_user, plan, now, provider
    ):
        subs.grant_free(
            company.pk, plan, period_end=now + timedelta(seconds=1), by=None, reason="T"
        )
        Subscription.objects.filter(company=company).update(period_end=now - timedelta(minutes=1))
        subs.expire_lapsed_subscriptions()
        assert provider.ended == []

    def test_an_expired_company_buys_again_through_checkout_and_gets_full_access(
        self, running, owner, provider, plan, now
    ):
        owner.post(CANCEL)
        Subscription.objects.filter(company=running).update(
            period_end=timezone.now() - timedelta(minutes=1)
        )
        subs.expire_lapsed_subscriptions()
        subs.activate(
            running.pk, plan, period_start=now, period_end=now + timedelta(days=30),
            stripe_customer_id=CUSTOMER, stripe_subscription_id="sub_test_2",
        )  # fmt: skip
        assert current(running).state == State.ACTIVE
        assert subs.can_upload(running.pk)

    def test_the_provider_failing_to_end_it_does_not_block_the_expiry(self, running, plan, now):
        send(payment_failed_event(running, plan, created=now))
        Subscription.objects.filter(company=running).update(past_due_since=now - timedelta(days=8))
        with override_settings(STRIPE_SECRET_KEY=""):
            assert subs.expire_lapsed_subscriptions() == 1
        assert current(running).state == State.EXPIRED


class TestBillingPortal:
    def test_the_owner_gets_the_providers_page_for_the_companys_own_customer(
        self, running, owner, provider
    ):
        assert owner.post(PORTAL).json() == {"url": "https://billing.example.test/session"}
        assert provider.portals[0]["customer_id"] == CUSTOMER

    def test_a_customer_id_in_the_request_is_never_used(self, running, owner, provider):
        owner.post(PORTAL, {"customer_id": "cus_somebody_else"}, format="json")
        assert provider.portals[0]["customer_id"] == CUSTOMER

    def test_the_return_address_is_fixed_to_the_app(self, running, owner, provider):
        owner.post(PORTAL, {"return_url": "https://evil.example.test"}, format="json")
        with override_settings(WEB_BASE_URL="https://app.example.test"):
            owner.post(PORTAL)
        assert provider.portals[0]["return_url"].endswith("/company/billing?portal=returned")
        assert "evil" not in provider.portals[0]["return_url"]
        assert provider.portals[1]["return_url"] == (
            "https://app.example.test/company/billing?portal=returned"
        )

    @pytest.mark.parametrize("state", ["past_due", "cancelled", "expired"])
    def test_it_opens_in_every_state_that_has_a_customer(self, running, owner, provider, state):
        Subscription.objects.filter(company=running).update(
            state=state, past_due_since=timezone.now()
        )
        assert owner.post(PORTAL).status_code == 200

    def test_a_company_that_never_paid_by_card_has_no_billing_page(self, company, owner, provider):
        reply = owner.post(PORTAL)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "no_billing_account")
        assert provider.portals == []

    def test_only_the_owner_may_open_it(self, running, provider):
        member = client_of(make_company_user(running, role="member"))
        assert member.post(PORTAL).status_code == 403
        assert provider.portals == []

    def test_a_visitor_may_not(self, provider):
        assert APIClient().post(PORTAL).status_code in (401, 403)

    def test_opening_it_is_a_security_event_of_the_audit_log(self, running, owner, provider):
        owner.post(PORTAL)
        entry = AuditEvent.objects.get(kind="security.billing_portal_opened")
        assert (entry.actor_kind, entry.company_id) == ("company", running.pk)

    def test_a_refused_opening_leaves_no_event(self, company, owner, provider):
        owner.post(PORTAL)
        assert not AuditEvent.objects.filter(kind="security.billing_portal_opened").exists()

    def test_a_provider_failure_gives_one_plain_sentence(self, running, owner):
        def fail(**sent):
            raise AppError("payment_provider_error", "Plain.", status_code=502)

        with patch.object(stripe_client, "create_portal_session", fail):
            assert owner.post(PORTAL).status_code == 502

    def test_coming_back_from_the_page_restores_nothing_by_itself(
        self, running, plan, owner, provider, now
    ):
        send(payment_failed_event(running, plan, created=now))
        owner.post(PORTAL)
        shown = owner.get("/api/company/usage/").json()
        assert shown["state"] == "past_due" and shown["can_manage_billing"] is True

    def test_a_company_with_a_customer_is_shown_the_button_and_one_without_is_not(
        self, running, owner, company
    ):
        assert owner.get("/api/company/usage/").json()["can_manage_billing"] is True
        other = make_company()
        client = client_of(make_company_user(other, role="owner"))
        assert client.get("/api/company/usage/").json()["can_manage_billing"] is False


class TestRenewalEmail:
    def mail_text(self):
        (mail,) = mails("subscription_renewing")
        return mail.text_body

    def test_the_owner_is_emailed_seven_days_before_with_the_date_and_amount(self, running, now):
        Subscription.objects.filter(company=running).update(
            period_end=now + timedelta(days=6, hours=23)
        )
        assert send_renewal_notices() == 1
        text = self.mail_text()
        assert "Fake Plan" in text and "USD 10.00" in text

    def test_not_earlier_than_the_days_before(self, running, now):
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=8))
        assert send_renewal_notices() == 0

    def test_only_once_for_a_period(self, running, now):
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=5))
        send_renewal_notices(), send_renewal_notices()
        assert len(mails("subscription_renewing")) == 1

    def test_the_next_period_gets_its_own_email(self, running, now):
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=5))
        send_renewal_notices()
        Subscription.objects.filter(company=running).update(
            period_end=now + timedelta(days=6, hours=1)
        )
        send_renewal_notices()
        assert len(mails("subscription_renewing")) == 2

    def test_the_days_come_from_the_setting(self, running, now):
        set_setting("notifications.subscription_ending_days", 3)
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=5))
        assert send_renewal_notices() == 0
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=2))
        assert send_renewal_notices() == 1

    def test_a_cancelled_subscription_gets_no_renewal_email(self, running, owner, provider, now):
        owner.post(CANCEL)
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=5))
        assert send_renewal_notices() == 0

    def test_a_subscription_that_does_not_charge_the_card_gets_none(
        self, company, owner_user, plan, now
    ):
        subs.grant_free(company.pk, plan, period_end=now + timedelta(days=5), by=None, reason="T")
        assert send_renewal_notices() == 0

    def test_a_waiting_downgrade_shows_the_lower_amount(self, running, now):
        smaller = plan_of("Fake Smaller", "4.00")
        Subscription.objects.filter(company=running).update(
            period_end=now + timedelta(days=5),
            pending_plan=smaller, pending_change="downgrade", pending_since=now,
        )  # fmt: skip
        send_renewal_notices()
        text = self.mail_text()
        assert "Fake Smaller" in text and "USD 4.00" in text

    def test_it_cannot_be_switched_off(self, running, owner_user, now):
        from notifications.service import set_choice

        with pytest.raises(AppError):
            set_choice(owner_user, "subscription_renewing", False)
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=5))
        assert send_renewal_notices() == 1

    def test_a_company_that_is_being_deleted_gets_none(self, running, now):
        running.__class__.objects.filter(pk=running.pk).update(status="pending_deletion")
        Subscription.objects.filter(company=running).update(period_end=now + timedelta(days=5))
        assert send_renewal_notices() == 0


class TestTheProviderClient:
    def test_the_renewal_is_stopped_at_the_period_end(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(stripe.Subscription, "retrieve", return_value={"status": "active"}),
            patch.object(stripe.Subscription, "modify") as modify,
        ):
            assert stripe_client.set_renewal_stops_at_period_end(SUB, True) is True
        assert modify.call_args.kwargs["cancel_at_period_end"] is True
        assert modify.call_args.kwargs["idempotency_key"]

    def test_an_ended_subscription_is_reported_not_changed(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(stripe.Subscription, "retrieve", return_value={"status": "canceled"}),
            patch.object(stripe.Subscription, "modify") as modify,
        ):
            assert stripe_client.set_renewal_stops_at_period_end(SUB, False) is False
        modify.assert_not_called()

    def test_a_provider_error_becomes_the_plain_message(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Subscription, "retrieve", side_effect=stripe.APIConnectionError("secret")
            ),
            pytest.raises(AppError) as caught,
        ):
            stripe_client.set_renewal_stops_at_period_end(SUB, True)
        assert "secret" not in caught.value.message

    def test_ending_a_running_subscription_cancels_it(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(stripe.Subscription, "retrieve", return_value={"status": "past_due"}),
            patch.object(stripe.Subscription, "cancel") as cancel,
        ):
            assert stripe_client.end_subscription(SUB) is True
        cancel.assert_called_once()

    def test_ending_one_that_already_ended_asks_for_nothing_more(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(stripe.Subscription, "retrieve", return_value={"status": "canceled"}),
            patch.object(stripe.Subscription, "cancel") as cancel,
        ):
            assert stripe_client.end_subscription(SUB) is True
        cancel.assert_not_called()

    def test_a_failure_while_ending_is_reported_as_false(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.Subscription, "retrieve", side_effect=stripe.APIConnectionError("x")
            ),
        ):
            assert stripe_client.end_subscription(SUB) is False

    def test_the_portal_session_is_made_for_the_customer_and_the_return_address_only(self):
        with (
            override_settings(STRIPE_SECRET_KEY=TEST_KEY),
            patch.object(
                stripe.billing_portal.Session,
                "create",
                return_value={"url": "https://x.example.test/p"},
            ) as create,
        ):
            url = stripe_client.create_portal_session(
                customer_id=CUSTOMER, return_url="https://app.example.test/back"
            )
        assert url == "https://x.example.test/p"
        sent = create.call_args.kwargs
        assert (sent["customer"], sent["return_url"]) == (CUSTOMER, "https://app.example.test/back")
        assert set(sent) == {"api_key", "max_network_retries", "customer", "return_url"}

    def test_a_key_that_is_not_a_test_key_is_refused(self):
        with override_settings(STRIPE_SECRET_KEY="sk_live_x"):  # nosecret: fake
            with pytest.raises(AppError) as caught:
                stripe_client.create_portal_session(
                    customer_id=CUSTOMER, return_url="https://a.test/"
                )
        assert caught.value.code == stripe_client.UNAVAILABLE_CODE
