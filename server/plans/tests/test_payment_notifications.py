import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user
from emailing.models import OutgoingEmail
from plans import subscriptions as subs
from plans.models import PaymentEvent, PendingPlanChange, Plan, Subscription
from usage import service as usage

pytestmark = pytest.mark.django_db
URL = "/api/payments/stripe/webhook/"
SECRET = "whsec_only3b7d1f9a5c2e8046"  # nosecret: fake
SUB = "sub_test_1"
State = Subscription.State


def at(month, day=15, hour=12):
    return datetime(2030, month, day, hour, tzinfo=UTC)


def stamp(moment):
    return int(moment.timestamp())


def sign(body, secret=SECRET, moment=None):
    moment = moment or int(time.time())
    digest = hmac.new(secret.encode(), f"{moment}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"t={moment},v1={digest}"


@pytest.fixture(autouse=True)
def webhook_secret():
    with override_settings(STRIPE_WEBHOOK_SECRET=SECRET):
        yield


def send(event, *, secret=SECRET, signed_at=None, header=None):
    body = json.dumps(event)
    return APIClient().post(
        URL,
        body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header if header is not None else sign(body, secret, signed_at),
    )


def event_of(kind, obj, *, event_id=None, created=None):
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:12]}",
        "object": "event",
        "type": kind,
        "created": stamp(created or at(1, 20)),
        "data": {"object": obj},
    }


def invoice(
    company, plan, *, start, end, reason="subscription_cycle", amount=1000, sub=SUB, **extra
):
    return {
        "id": f"in_{uuid.uuid4().hex[:12]}",
        "object": "invoice",
        "customer": "cus_test_1",
        "subscription": sub,
        "subscription_details": {
            "metadata": {"company_id": str(company.pk), "plan_id": str(plan.pk)}
        },
        "billing_reason": reason,
        "amount_paid": amount,
        "amount_due": amount,
        "currency": "usd",
        "attempt_count": 1,
        "lines": {"data": [{"period": {"start": stamp(start), "end": stamp(end)}}]},
        **extra,
    }


def paid(company, plan, **options):
    created = options.pop("created", None)
    event_id = options.pop("event_id", None)
    return event_of(
        "invoice.paid", invoice(company, plan, **options), event_id=event_id, created=created
    )


def failed(company, plan, **options):
    created = options.pop("created", None)
    event_id = options.pop("event_id", None)
    return event_of(
        "invoice.payment_failed",
        invoice(company, plan, **options),
        event_id=event_id,
        created=created,
    )


@pytest.fixture
def company():
    company = make_company()
    make_company_user(company, role="owner")
    return company


@pytest.fixture
def plan():
    return Plan.objects.create(
        name="Fake Plan",
        status="active",
        price_usd=Decimal("10"),
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=1000,
    )


@pytest.fixture
def subscribed(company, plan):
    """A company activated by checkout: period January 15 to February 15, linked to Stripe."""
    subs.activate(
        company.pk,
        plan,
        period_start=at(1),
        period_end=at(2),
        stripe_customer_id="cus_test_1",
        stripe_subscription_id=SUB,
    )
    return company


def current(company):
    return Subscription.objects.get(company=company)


def mails(company, template):
    owner = company.companyuser_set.first() if hasattr(company, "companyuser_set") else None
    return [
        m
        for m in OutgoingEmail.objects.all()
        if m.template == template and (owner is None or m.to_address == owner.email)
    ]


class TestOnlyGenuineNoticesAreRead:
    def test_a_signed_notice_is_accepted(self, subscribed, plan):
        assert send(paid(subscribed, plan, start=at(2), end=at(3))).status_code == 200

    @pytest.mark.parametrize(
        "how",
        [
            {"header": ""},
            {"header": "t=1,v1=abc"},
            {"header": "garbage"},
            {"secret": "whsec_another0000000000000000"},  # nosecret: fake
            {"signed_at": int(time.time()) - 3600},
        ],
    )
    def test_an_unverified_notice_is_refused_and_changes_nothing(self, subscribed, plan, how):
        reply = send(paid(subscribed, plan, start=at(2), end=at(3)), **how)
        assert (reply.status_code, reply.json()["error"]["code"]) == (400, "invalid_signature")
        assert PaymentEvent.objects.count() == 0
        assert current(subscribed).period_end == at(2)

    def test_a_body_changed_after_signing_is_refused(self, subscribed, plan):
        event = paid(subscribed, plan, start=at(2), end=at(3))
        header = sign(json.dumps(event))
        event["data"]["object"]["amount_paid"] = 1
        assert send(event, header=header).status_code == 400
        assert PaymentEvent.objects.count() == 0

    def test_without_a_configured_secret_everything_is_refused(self, subscribed, plan):
        with override_settings(STRIPE_WEBHOOK_SECRET=""):
            assert send(paid(subscribed, plan, start=at(2), end=at(3))).status_code == 400

    def test_a_visitor_with_no_signature_is_refused(self):
        assert APIClient().post(URL, "{}", content_type="application/json").status_code == 400

    def test_a_notice_of_another_type_is_acknowledged_and_ignored(self, subscribed):
        reply = send(event_of("customer.created", {"object": "customer"}))
        assert (reply.status_code, reply.json()["outcome"]) == (200, "ignored")

    def test_a_notice_for_an_unknown_company_changes_nothing(self, plan):
        stranger = make_company()
        event = paid(stranger, plan, start=at(2), end=at(3), sub="sub_unknown")
        event["data"]["object"]["subscription_details"]["metadata"] = {"company_id": "999999"}
        reply = send(event)
        assert (reply.status_code, reply.json()["outcome"]) == (200, "unmatched")
        assert PaymentEvent.objects.count() == 0


class TestPaidInvoice:
    def test_a_renewal_records_the_payment_and_moves_to_the_invoices_own_period(
        self, subscribed, plan
    ):
        reply = send(paid(subscribed, plan, start=at(2), end=at(3, 15, 13), event_id="evt_r1"))
        assert reply.json()["outcome"] == "handled"
        subscription = current(subscribed)
        assert (subscription.period_start, subscription.period_end) == (at(2), at(3, 15, 13))
        assert subscription.state == State.ACTIVE
        record = PaymentEvent.objects.get()
        assert (record.provider_event_id, record.amount_minor, record.currency, record.kind) == (
            "evt_r1",
            1000,
            "USD",
            "payment",
        )
        assert (record.company_id, record.plan_id) == (subscribed.pk, plan.pk)

    def test_the_period_is_stripes_never_one_month_from_our_side(self, subscribed, plan):
        send(paid(subscribed, plan, start=at(2), end=at(3, 20)))
        assert current(subscribed).period_end == at(3, 20)

    def test_the_first_invoice_after_checkout_does_not_extend_again(self, subscribed, plan):
        before = current(subscribed)
        send(
            paid(
                subscribed,
                plan,
                start=at(1, 15, 11),
                end=at(2, 15, 11),
                reason="subscription_create",
            )
        )
        after = current(subscribed)
        assert (after.period_start, after.period_end) == (before.period_start, before.period_end)
        assert PaymentEvent.objects.count() == 1

    def test_even_with_other_dates_the_first_invoice_does_not_extend(self, subscribed, plan):
        send(paid(subscribed, plan, start=at(1), end=at(3), reason="subscription_create"))
        assert current(subscribed).period_end == at(2)

    def test_the_first_invoice_before_the_buyer_is_back_activates_and_checkout_then_adds_nothing(
        self, company, plan
    ):
        send(paid(company, plan, start=at(1), end=at(2), reason="subscription_create"))
        subscription = current(company)
        assert (subscription.state, subscription.plan_id, subscription.period_end) == (
            State.ACTIVE,
            plan.pk,
            at(2),
        )
        assert (subscription.stripe_customer_id, subscription.stripe_subscription_id) == (
            "cus_test_1",
            SUB,
        )

    def test_the_same_notice_twice_changes_nothing_the_second_time(self, subscribed, plan):
        event = paid(subscribed, plan, start=at(2), end=at(3), event_id="evt_same")
        send(event)
        stamp_after_first = current(subscribed).updated_at
        reply = send(event)
        assert reply.json()["outcome"] == "duplicate"
        assert PaymentEvent.objects.count() == 1
        assert current(subscribed).updated_at == stamp_after_first

    def test_an_older_period_arriving_late_does_not_move_back(self, subscribed, plan):
        send(paid(subscribed, plan, start=at(3), end=at(4), event_id="evt_new"))
        send(paid(subscribed, plan, start=at(2), end=at(3), event_id="evt_old"))
        assert current(subscribed).period_end == at(4)
        assert PaymentEvent.objects.count() == 2  # both payments really happened

    def test_a_paid_invoice_clears_past_due(self, subscribed, plan):
        subs.mark_past_due(subscribed.pk)
        send(paid(subscribed, plan, start=at(2), end=at(3)))
        subscription = current(subscribed)
        assert (subscription.state, subscription.past_due_since) == (State.ACTIVE, None)

    def test_a_waiting_price_change_takes_effect_with_the_new_period(self, subscribed, plan):
        PendingPlanChange.objects.create(plan=plan, values={"price_usd": "12.00"})
        send(paid(subscribed, plan, start=at(2), end=at(3)))
        plan.refresh_from_db()
        assert plan.price_usd == Decimal("12.00")

    def test_a_subscription_of_another_stripe_id_does_not_move_the_period(self, subscribed, plan):
        send(paid(subscribed, plan, start=at(2), end=at(3), sub="sub_other"))
        assert current(subscribed).period_end == at(2)

    def test_the_payment_amount_is_kept_exactly(self, subscribed, plan):
        send(paid(subscribed, plan, start=at(2), end=at(3), amount=1234))
        assert PaymentEvent.objects.get().amount_minor == 1234

    def test_a_paid_invoice_without_a_period_still_records_the_payment(self, subscribed, plan):
        event = paid(subscribed, plan, start=at(2), end=at(3))
        event["data"]["object"]["lines"] = {"data": []}
        send(event)
        assert (PaymentEvent.objects.count(), current(subscribed).period_end) == (1, at(2))

    def test_the_newer_api_shape_with_the_subscription_under_parent_is_read(self, subscribed, plan):
        event = paid(subscribed, plan, start=at(2), end=at(3))
        obj = event["data"]["object"]
        details = {"subscription": SUB, "metadata": obj.pop("subscription_details")["metadata"]}
        del obj["subscription"]
        obj["parent"] = {"subscription_details": details}
        send(event)
        assert current(subscribed).period_end == at(3)


class TestUsageStartsFresh:
    def test_the_new_period_counts_from_zero_and_the_old_one_keeps_its_numbers(
        self, subscribed, plan
    ):
        cv = uuid.uuid4()
        usage.accept_cv(subscribed.pk, cv, now=at(1, 20))
        usage.mark_scored(subscribed.pk, cv)
        send(paid(subscribed, plan, start=at(2), end=at(3)))
        assert usage.current_usage(subscribed.pk, now=at(2, 20))["cvs_scored"] == 0
        assert usage.current_usage(subscribed.pk, now=at(1, 25))["cvs_scored"] == 1

    def test_nothing_carries_over_into_the_new_period(self, subscribed, plan):
        for _ in range(3):
            cv = uuid.uuid4()
            usage.accept_cv(subscribed.pk, cv, now=at(1, 20))
            usage.mark_scored(subscribed.pk, cv)
        send(paid(subscribed, plan, start=at(2), end=at(3)))
        cv = uuid.uuid4()
        usage.accept_cv(subscribed.pk, cv, now=at(2, 20))
        usage.mark_scored(subscribed.pk, cv)
        assert usage.current_usage(subscribed.pk, now=at(2, 21))["cvs_scored"] == 1


class TestFailedPayment:
    def test_it_makes_the_company_past_due_and_emails_the_owner_once(self, subscribed, plan):
        send(failed(subscribed, plan, start=at(2), end=at(3), event_id="evt_f1"))
        subscription = current(subscribed)
        assert (subscription.state, subscription.past_due_since is not None) == (
            State.PAST_DUE,
            True,
        )
        assert len(mails(subscribed, "payment_problem")) == 1

    def test_the_failure_is_recorded_with_its_reason(self, subscribed, plan):
        send(failed(subscribed, plan, start=at(2), end=at(3), amount=1000, attempt_count=2))
        record = PaymentEvent.objects.get()
        assert (record.kind, record.amount_minor, record.reason) == (
            "failure",
            1000,
            "Payment attempt 2 failed.",
        )

    def test_the_same_notice_twice_sends_one_email(self, subscribed, plan):
        event = failed(subscribed, plan, start=at(2), end=at(3), event_id="evt_f1")
        send(event), send(event)
        assert PaymentEvent.objects.count() == 1
        assert len(mails(subscribed, "payment_problem")) == 1

    def test_a_second_attempt_failing_keeps_the_first_date_and_sends_no_second_email(
        self, subscribed, plan
    ):
        send(failed(subscribed, plan, start=at(2), end=at(3), event_id="evt_f1"))
        first = current(subscribed).past_due_since
        send(failed(subscribed, plan, start=at(2), end=at(3), event_id="evt_f2", attempt_count=2))
        assert current(subscribed).past_due_since == first
        assert PaymentEvent.objects.count() == 2
        assert len(mails(subscribed, "payment_problem")) == 1

    def test_a_failure_delivered_after_a_later_payment_is_recorded_but_changes_nothing(
        self, subscribed, plan
    ):
        send(paid(subscribed, plan, start=at(2), end=at(3), created=at(2, 16)))
        send(failed(subscribed, plan, start=at(2), end=at(3), created=at(2, 15, 13)))
        assert current(subscribed).state == State.ACTIVE
        assert PaymentEvent.objects.filter(kind="failure").count() == 1

    def test_a_failure_before_payment_then_the_payment_brings_it_back(self, subscribed, plan):
        send(failed(subscribed, plan, start=at(2), end=at(3), created=at(2, 15, 13)))
        assert current(subscribed).state == State.PAST_DUE
        send(paid(subscribed, plan, start=at(2), end=at(3), created=at(2, 16)))
        assert current(subscribed).state == State.ACTIVE

    def test_a_failed_first_invoice_makes_nobody_past_due(self, company, plan):
        send(failed(company, plan, start=at(1), end=at(2), reason="subscription_create"))
        assert current(company).state == State.NO_PLAN
        assert PaymentEvent.objects.filter(kind="failure").count() == 1

    def test_a_failure_of_another_stripe_subscription_changes_nothing(self, subscribed, plan):
        send(failed(subscribed, plan, start=at(2), end=at(3), sub="sub_other"))
        assert current(subscribed).state == State.ACTIVE

    def test_the_owner_keeps_full_access_while_past_due(self, subscribed, plan):
        send(failed(subscribed, plan, start=at(2), end=at(3)))
        assert subs.can_upload(subscribed.pk)


class TestCancellation:
    def cancelled(self, sub=SUB):
        return event_of(
            "customer.subscription.deleted", {"object": "subscription", "id": sub, "metadata": {}}
        )

    def test_renewal_stops_and_access_runs_to_the_period_end(self, subscribed):
        send(self.cancelled())
        subscription = current(subscribed)
        assert (subscription.state, subscription.renewal, subscription.period_end) == (
            State.CANCELLED,
            False,
            at(2),
        )
        assert subs.can_upload(subscribed.pk)

    def test_after_the_period_end_access_ends(self, subscribed):
        send(self.cancelled())
        assert subs.effective_state(current(subscribed), now=at(2, 16)) == State.EXPIRED

    def test_the_owner_is_emailed(self, subscribed):
        send(self.cancelled())
        assert len(mails(subscribed, "usage_notice")) == 2  # active, then cancelled

    def test_the_same_notice_twice_changes_nothing_more(self, subscribed):
        event = self.cancelled()
        send(event), send(event)
        assert current(subscribed).state == State.CANCELLED

    def test_the_end_of_an_old_subscription_leaves_a_newer_one_alone(self, subscribed):
        send(self.cancelled("sub_old"))
        assert current(subscribed).state == State.ACTIVE

    def test_an_unknown_subscription_changes_nothing(self):
        assert send(self.cancelled("sub_nobody")).json()["outcome"] == "unmatched"

    def test_a_past_due_company_is_left_to_its_grace_period(self, subscribed, plan):
        subs.mark_past_due(subscribed.pk)
        send(self.cancelled())
        assert current(subscribed).state == State.PAST_DUE


class TestRealMoneyOnly:
    def test_checkout_alone_records_no_payment(self, subscribed):
        assert PaymentEvent.objects.count() == 0
