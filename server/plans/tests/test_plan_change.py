import json
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditEvent
from companies.models import CompanyUser
from core.tests.factories import make_company, make_company_user
from emailing.models import OutgoingEmail
from plans import stripe_client
from plans import subscriptions as subs
from plans.limits import check_projects, check_team_size
from plans.models import LimitOverride, PaymentEvent, Plan, Subscription
from plans.plan_change import over_limits
from plans.stripe_client import APPLIED, DECLINED, NEEDS_ACTION, PriceChange
from plans.tests.test_payment_notifications import SECRET, event_of, send, stamp
from plans.tests.test_regional_pricing import LIMITS
from projects.models import Project
from signin import service
from usage import service as usage

pytestmark = pytest.mark.django_db
CHANGE = "/api/company/billing/change-plan/"
CANCEL = "/api/company/billing/change-plan/cancel/"
USAGE = "/api/company/usage/"
SUB = "sub_test_1"
TEST_KEY = "sk_test_only9c4e7a1b5d2f8e63"  # nosecret: fake
Change = Subscription.Change


def plan_of(name, usd, **fields):
    return Plan.objects.create(
        name=name, price_usd=Decimal(usd), **{"status": "active", **LIMITS, **fields}
    )


def limit_warnings():
    return [
        mail
        for mail in OutgoingEmail.objects.filter(template="usage_notice")
        if "over its plan limits" in mail.subject
    ]


class FakeProvider:
    """Stands in for the payment provider: remembers every price change that was asked."""

    def __init__(self):
        self.calls = []
        self.outcome = PriceChange(APPLIED)

    def change(self, **sent):
        self.calls.append(sent)
        return self.outcome


@pytest.fixture
def provider():
    fake = FakeProvider()
    with patch.object(stripe_client, "change_subscription_price", fake.change):
        yield fake


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner_user(company):
    return make_company_user(company, role="owner")


def client_of(person):
    issued = service.start_session(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def owner(owner_user):
    return client_of(owner_user)


@pytest.fixture
def small():
    return plan_of("Fake Small", "10.00", max_projects=2, max_team_accounts=2, cvs_per_month=5)


@pytest.fixture
def big():
    return plan_of("Fake Big", "30.00", max_projects=10, max_team_accounts=10, cvs_per_month=50)


@pytest.fixture
def middle():
    return plan_of("Fake Middle", "20.00", max_projects=5, max_team_accounts=5, cvs_per_month=20)


@pytest.fixture
def now():
    return timezone.now()


def subscribe(company, plan, now):
    subs.activate(
        company.pk,
        plan,
        period_start=now - timedelta(days=10),
        period_end=now + timedelta(days=20),
        stripe_customer_id="cus_test_1",
        stripe_subscription_id=SUB,
    )


@pytest.fixture
def on_big(company, owner_user, big, now):
    subscribe(company, big, now)
    return company


@pytest.fixture
def on_small(company, owner_user, small, now):
    subscribe(company, small, now)
    return company


def current(company):
    return Subscription.objects.get(company=company)


def ask(client, plan):
    return client.post(CHANGE, {"plan_id": plan.pk}, format="json")


def add_projects(company, owner_user, count):
    for number in range(count):
        Project.objects.create(
            company=company, title=f"Fake {number}", job_description="d",
            reading_model="m", created_by=owner_user,
        )  # fmt: skip


def paid_upgrade_event(company, plan, *, start, end, event_id=None, amount=500):
    invoice = {
        "object": "invoice",
        "customer": "cus_test_1",
        "subscription": SUB,
        "subscription_details": {"metadata": {"company_id": str(company.pk)}},
        "billing_reason": "subscription_update",
        "amount_paid": amount,
        "amount_due": amount,
        "currency": "usd",
        "lines": {"data": [{"period": {"start": stamp(start), "end": stamp(end)}}]},
    }
    return event_of("invoice.paid", invoice, event_id=event_id, created=timezone.now())


def renewal_event(company, *, start, end, event_id=None, amount=1000):
    invoice = {
        "object": "invoice",
        "customer": "cus_test_1",
        "subscription": SUB,
        "subscription_details": {"metadata": {"company_id": str(company.pk), "plan_id": "0"}},
        "billing_reason": "subscription_cycle",
        "amount_paid": amount,
        "amount_due": amount,
        "currency": "usd",
        "lines": {"data": [{"period": {"start": stamp(start), "end": stamp(end)}}]},
    }
    return event_of("invoice.paid", invoice, event_id=event_id, created=timezone.now())


@pytest.fixture(autouse=True)
def webhook_secret():
    with override_settings(STRIPE_WEBHOOK_SECRET=SECRET):
        yield


class TestUpgrade:
    def test_the_provider_is_asked_to_charge_the_difference_now(
        self, on_small, owner, provider, big
    ):
        reply = ask(owner, big)
        assert (reply.status_code, reply.json()["result"]) == (200, "processing")
        sent = provider.calls[0]
        assert sent["immediate"] is True
        assert (sent["amount_minor"], sent["currency"]) == (3000, "USD")
        assert sent["subscription_id"] == SUB

    def test_the_plan_does_not_change_until_the_paid_notice_arrives(
        self, on_small, owner, provider, big, small
    ):
        ask(owner, big)
        waiting = current(on_small)
        assert waiting.plan == small
        assert (waiting.pending_plan, waiting.pending_change) == (big, Change.UPGRADE)

    def test_the_billing_screen_shows_it_as_processing(self, on_small, owner, provider, big):
        ask(owner, big)
        shown = owner.get(USAGE).json()
        assert shown["plan_name"] == "Fake Small"
        assert shown["pending_change"]["processing"] is True
        assert shown["pending_change"]["plan_name"] == "Fake Big"

    def test_the_paid_notice_changes_the_plan_and_keeps_the_period(
        self, on_small, owner, provider, big, now
    ):
        before = current(on_small)
        ask(owner, big)
        reply = send(
            paid_upgrade_event(on_small, big, start=now, end=before.period_end),
        )
        assert reply.status_code == 200
        after = current(on_small)
        assert after.plan == big and after.state == "active"
        assert (after.period_start, after.period_end) == (before.period_start, before.period_end)
        assert (after.pending_plan, after.pending_change) == (None, "")

    def test_the_payment_is_recorded_once_and_a_repeat_changes_nothing(
        self, on_small, owner, provider, big, now
    ):
        ask(owner, big)
        event = paid_upgrade_event(on_small, big, start=now, end=now, event_id="evt_up_1")
        send(event), send(event)
        assert PaymentEvent.objects.filter(company=on_small, kind="payment").count() == 1
        assert PaymentEvent.objects.get(company=on_small).plan == big

    def test_used_counts_carry_over(self, on_small, owner, provider, big, now):
        for _ in range(3):
            cv = uuid.uuid4()
            usage.accept_cv(on_small.pk, cv)
            usage.mark_scored(on_small.pk, cv)
        ask(owner, big)
        send(paid_upgrade_event(on_small, big, start=now, end=now))
        assert usage.current_usage(on_small.pk)["cvs_scored"] == 3
        assert owner.get(USAGE).json()["cvs"]["limit"] == 50

    def test_a_declined_card_changes_nothing_and_says_so(
        self, on_small, owner, provider, big, small
    ):
        provider.outcome = PriceChange(DECLINED)
        reply = ask(owner, big)
        assert (reply.status_code, reply.json()["error"]["code"]) == (402, "payment_declined")
        assert "plan has not changed" in reply.json()["error"]["message"]
        waiting = current(on_small)
        assert waiting.plan == small and waiting.pending_plan is None

    def test_a_declined_upgrade_leaves_a_waiting_downgrade_alone(
        self, on_big, owner, provider, small, middle
    ):
        ask(owner, small)
        provider.outcome = PriceChange(DECLINED)
        assert ask(owner, plan_of("Fake Huge", "50.00")).status_code == 402
        assert current(on_big).pending_plan == small

    def test_a_bank_check_returns_the_page_to_finish_it(self, on_small, owner, provider, big):
        provider.outcome = PriceChange(NEEDS_ACTION, url="https://pay.example.test/check")
        body = ask(owner, big).json()
        assert (body["result"], body["url"]) == (
            "action_required",
            "https://pay.example.test/check",
        )
        assert current(on_small).pending_change == Change.UPGRADE

    def test_a_second_click_while_processing_charges_nothing_more(
        self, on_small, owner, provider, big
    ):
        ask(owner, big)
        reply = ask(owner, big)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "plan_change_processing")
        assert len(provider.calls) == 1

    def test_an_upgrade_that_never_got_its_notice_can_be_asked_again(
        self, on_small, owner, provider, big
    ):
        ask(owner, big)
        Subscription.objects.filter(company=on_small).update(
            pending_since=timezone.now() - timedelta(hours=3)
        )
        assert ask(owner, big).status_code == 200
        assert len(provider.calls) == 2

    def test_an_upgrade_replaces_a_waiting_downgrade(
        self, on_big, owner, provider, big, small, middle
    ):
        ask(owner, small)
        reply = ask(owner, plan_of("Fake Huge", "50.00"))
        assert reply.status_code == 200
        assert current(on_big).pending_change == Change.UPGRADE

    def test_a_paid_upgrade_notice_with_nothing_waiting_changes_no_plan(
        self, on_small, small, big, now
    ):
        send(paid_upgrade_event(on_small, big, start=now, end=now))
        assert current(on_small).plan == small

    def test_the_following_renewal_keeps_the_upgraded_plan(
        self, on_small, owner, provider, big, now
    ):
        ask(owner, big)
        subscription = current(on_small)
        send(paid_upgrade_event(on_small, big, start=now, end=subscription.period_end))
        send(
            renewal_event(
                on_small,
                start=subscription.period_end,
                end=subscription.period_end + timedelta(days=30),
            )
        )
        assert current(on_small).plan == big


class TestDowngrade:
    def test_the_provider_price_changes_with_nothing_charged_or_credited(
        self, on_big, owner, provider, small
    ):
        reply = ask(owner, small)
        assert (reply.status_code, reply.json()["result"]) == (200, "downgrade_scheduled")
        sent = provider.calls[0]
        assert (sent["immediate"], sent["amount_minor"]) == (False, 1000)

    def test_the_plan_stays_until_the_renewal(self, on_big, owner, provider, big, small):
        ask(owner, small)
        waiting = current(on_big)
        assert waiting.plan == big
        assert (waiting.pending_plan, waiting.pending_change) == (small, Change.DOWNGRADE)
        shown = owner.get(USAGE).json()["pending_change"]
        assert shown["kind"] == "downgrade" and shown["processing"] is False
        assert shown["takes_effect"] is not None

    def test_the_renewal_applies_the_lower_plan_and_clears_the_wait(
        self, on_big, owner, provider, small
    ):
        ask(owner, small)
        end = current(on_big).period_end
        send(renewal_event(on_big, start=end, end=end + timedelta(days=30), amount=1000))
        after = current(on_big)
        assert after.plan == small
        assert after.period_end.replace(microsecond=0) == (end + timedelta(days=30)).replace(
            microsecond=0
        )
        assert (after.pending_plan, after.pending_change) == (None, "")
        assert PaymentEvent.objects.get(company=on_big).plan == small

    def test_the_renewal_applies_it_once_even_if_the_notice_repeats(
        self, on_big, owner, provider, small
    ):
        ask(owner, small)
        end = current(on_big).period_end
        event = renewal_event(on_big, start=end, end=end + timedelta(days=30), event_id="evt_r1")
        send(event), send(event)
        assert current(on_big).plan == small
        assert PaymentEvent.objects.filter(company=on_big).count() == 1

    def test_the_renewal_starts_usage_from_zero(self, on_big, owner, provider, small):
        cv = uuid.uuid4()
        usage.accept_cv(on_big.pk, cv)
        usage.mark_scored(on_big.pk, cv)
        ask(owner, small)
        end = current(on_big).period_end
        send(renewal_event(on_big, start=end, end=end + timedelta(days=30)))
        assert usage.current_usage(on_big.pk, now=end + timedelta(days=1))["cvs_scored"] == 0

    def test_a_renewal_without_a_waiting_downgrade_keeps_the_plan(self, on_big, big):
        end = current(on_big).period_end
        send(renewal_event(on_big, start=end, end=end + timedelta(days=30)))
        assert current(on_big).plan == big

    def test_blocked_below_the_projects_in_use_with_an_explanation(
        self, on_big, owner_user, owner, provider, small
    ):
        add_projects(on_big, owner_user, 4)
        reply = ask(owner, small)
        body = reply.json()["error"]
        assert (reply.status_code, body["code"]) == (409, "downgrade_blocked")
        assert "Projects: 4 in use, the plan allows 2 (2 over)" in body["message"]
        assert provider.calls == []
        assert current(on_big).pending_plan is None

    def test_blocked_below_the_cvs_used_this_month(self, on_big, owner, provider, small):
        for _ in range(6):
            cv = uuid.uuid4()
            usage.accept_cv(on_big.pk, cv)
            usage.mark_scored(on_big.pk, cv)
        body = ask(owner, small).json()["error"]
        assert body["code"] == "downgrade_blocked"
        assert "CVs this month: 6 in use, the plan allows 5 (1 over)" in body["message"]

    def test_waiting_cvs_count_too(self, on_big, owner, provider, small):
        for _ in range(6):
            usage.accept_cv(on_big.pk, uuid.uuid4())
        assert ask(owner, small).json()["error"]["code"] == "downgrade_blocked"

    def test_blocked_below_the_team_in_use_open_invitations_included(
        self, on_big, owner, provider, small
    ):
        make_company_user(on_big, role="member")
        make_company_user(on_big, role="member")
        body = ask(owner, small).json()["error"]
        assert body["code"] == "downgrade_blocked"
        assert "Team accounts and open invitations: 3 in use" in body["message"]

    def test_the_block_names_every_limit_that_is_over(
        self, on_big, owner_user, owner, provider, small
    ):
        add_projects(on_big, owner_user, 3)
        make_company_user(on_big, role="member")
        make_company_user(on_big, role="member")
        over = ask(owner, small).json()["error"]["details"]["over"]
        assert sorted(item["name"] for item in over) == ["max_projects", "max_team_accounts"]
        assert {item["over"] for item in over} == {1}

    def test_a_company_exactly_at_the_limit_may_downgrade(
        self, on_big, owner_user, owner, provider, small
    ):
        add_projects(on_big, owner_user, 2)
        assert ask(owner, small).status_code == 200

    def test_archived_projects_do_not_block(self, on_big, owner_user, owner, provider, small):
        add_projects(on_big, owner_user, 4)
        Project.objects.update(status=Project.Status.ARCHIVED)
        assert ask(owner, small).status_code == 200

    def test_a_company_limit_override_is_respected(
        self, on_big, owner_user, owner, provider, small
    ):
        add_projects(on_big, owner_user, 4)
        LimitOverride.objects.create(company=on_big, name="max_projects", value=6)
        assert ask(owner, small).status_code == 200

    def test_a_second_downgrade_replaces_the_first(self, on_big, owner, provider, small, middle):
        ask(owner, small)
        ask(owner, middle)
        assert current(on_big).pending_plan == middle
        assert len(provider.calls) == 2

    def test_a_provider_failure_leaves_nothing_waiting(self, on_big, owner, small):
        def fail(**sent):
            raise stripe_client.AppError(
                stripe_client.PROVIDER_CODE, stripe_client.PROVIDER_MESSAGE, status_code=502
            )

        with patch.object(stripe_client, "change_subscription_price", fail):
            reply = ask(owner, small)
        assert reply.status_code == 502
        assert current(on_big).pending_plan is None


class TestTooBigAfterTheRenewal:
    """Things that grew after the request: the lower plan applies anyway (the lower price was
    paid) and nothing is removed; new work is refused until the company is under the limit."""

    def grow_and_renew(self, company, owner_user, owner, provider, small):
        ask(owner, small)
        add_projects(company, owner_user, 4)
        make_company_user(company, role="member")
        make_company_user(company, role="member")
        end = current(company).period_end
        send(renewal_event(company, start=end, end=end + timedelta(days=30)))

    def test_the_lower_plan_applies_anyway(self, on_big, owner_user, owner, provider, small):
        self.grow_and_renew(on_big, owner_user, owner, provider, small)
        assert current(on_big).plan == small

    def test_nothing_is_deleted_or_removed(self, on_big, owner_user, owner, provider, small):
        self.grow_and_renew(on_big, owner_user, owner, provider, small)
        assert Project.objects.filter(company=on_big).count() == 4
        assert CompanyUser.objects.filter(company=on_big).exclude(status="removed").count() == 3

    def test_new_projects_and_invitations_are_refused_until_under_the_limit(
        self, on_big, owner_user, owner, provider, small
    ):
        self.grow_and_renew(on_big, owner_user, owner, provider, small)
        assert not check_projects(on_big.pk, 4).allowed
        assert not check_team_size(on_big.pk, 3).allowed
        assert check_projects(on_big.pk, 1).allowed  # under the limit again: allowed

    def test_the_owner_is_emailed_what_is_over_and_by_how_much(
        self, on_big, owner_user, owner, provider, small
    ):
        self.grow_and_renew(on_big, owner_user, owner, provider, small)
        (message,) = limit_warnings()
        text = message.text_body
        assert "Projects: 4 in use, the plan allows 2 (2 over)" in text
        assert "Nothing was deleted" in text

    def test_no_warning_is_sent_when_the_company_fits(self, on_big, owner, provider, small):
        ask(owner, small)
        end = current(on_big).period_end
        send(renewal_event(on_big, start=end, end=end + timedelta(days=30)))
        assert limit_warnings() == []

    def test_over_limits_lists_exact_numbers(self, on_big, owner_user, small):
        add_projects(on_big, owner_user, 5)
        found = {item["name"]: item for item in over_limits(on_big.pk, small)}
        assert (found["max_projects"]["used"], found["max_projects"]["limit"]) == (5, 2)


class TestCancellingADowngrade:
    def test_the_provider_price_returns_to_the_current_plan_without_proration(
        self, on_big, owner, provider, big, small
    ):
        ask(owner, small)
        assert owner.post(CANCEL).status_code == 200
        back = provider.calls[-1]
        assert back["immediate"] is False
        assert (back["plan"], back["amount_minor"]) == (big, 3000)
        assert back["subscription_id"] == SUB

    def test_the_waiting_plan_is_forgotten(self, on_big, owner, provider, big, small):
        ask(owner, small)
        owner.post(CANCEL)
        after = current(on_big)
        assert (after.plan, after.pending_plan, after.pending_change) == (big, None, "")

    def test_the_next_renewal_then_keeps_the_plan(self, on_big, owner, provider, big, small):
        ask(owner, small)
        owner.post(CANCEL)
        end = current(on_big).period_end
        send(renewal_event(on_big, start=end, end=end + timedelta(days=30), amount=3000))
        assert current(on_big).plan == big

    def test_a_failure_at_the_provider_keeps_the_downgrade_waiting(
        self, on_big, owner, provider, small
    ):
        ask(owner, small)

        def fail(**sent):
            raise stripe_client.AppError("payment_provider_error", "Plain.", status_code=502)

        with patch.object(stripe_client, "change_subscription_price", fail):
            assert owner.post(CANCEL).status_code == 502
        assert current(on_big).pending_plan == small

    def test_with_nothing_waiting_nothing_is_sent(self, on_big, owner, provider):
        reply = owner.post(CANCEL)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "no_downgrade_waiting")
        assert provider.calls == []

    def test_a_double_click_sends_one_price_change(self, on_big, owner, provider, small):
        ask(owner, small)
        owner.post(CANCEL), owner.post(CANCEL)
        assert len(provider.calls) == 2  # the downgrade, then one way back

    def test_it_is_audited(self, on_big, owner, provider, small):
        ask(owner, small)
        owner.post(CANCEL)
        kinds = list(
            AuditEvent.objects.filter(kind="plan.changed")
            .order_by("id")
            .values_list("details", flat=True)
        )
        assert [entry["kind"] for entry in kinds] == ["downgrade", "downgrade_cancelled"]


class TestWhoAndWhen:
    def test_only_the_owner_may_change_the_plan(self, on_big, provider, small):
        member = client_of(make_company_user(on_big, role="member"))
        assert ask(member, small).status_code == 403
        assert member.post(CANCEL).status_code == 403
        assert provider.calls == []

    def test_a_visitor_may_not(self, provider, small):
        assert APIClient().post(CHANGE, {"plan_id": small.pk}, format="json").status_code in (
            401,
            403,
        )

    def test_the_same_plan_is_refused(self, on_big, owner, provider, big):
        reply = ask(owner, big)
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "same_plan")

    @pytest.mark.parametrize("status", ["hidden", "archived"])
    def test_a_plan_not_for_sale_is_not_found(self, on_big, owner, provider, status):
        assert ask(owner, plan_of("Fake Gone", "5.00", status=status)).status_code == 404

    def test_an_unknown_plan_is_not_found(self, on_big, owner, provider):
        assert owner.post(CHANGE, {"plan_id": 999999}, format="json").status_code == 404

    @pytest.mark.parametrize("body", [{}, {"plan_id": "x"}, {"plan_id": 1, "company_id": 2}])
    def test_a_bad_request_is_refused_in_the_shared_shape(self, on_big, owner, provider, body):
        reply = owner.post(CHANGE, body, format="json")
        assert reply.status_code == 400 and reply.json()["error"]["code"]

    def test_a_company_with_no_plan_buys_through_checkout_instead(
        self, company, owner, provider, small
    ):
        reply = ask(owner, small)
        assert (reply.status_code, reply.json()["error"]["code"]) == (
            409,
            "plan_change_unavailable",
        )

    def test_a_free_grant_cannot_use_it(self, company, owner, provider, small, big, now):
        subs.grant_free(company.pk, small, period_end=now + timedelta(days=5), by=None, reason="T")
        assert ask(owner, big).json()["error"]["code"] == "plan_change_unavailable"

    def test_a_cancelled_subscription_cannot_change_plan(self, on_small, owner, provider, big):
        subs.cancel(on_small.pk)
        assert ask(owner, big).json()["error"]["code"] == "plan_change_unavailable"

    def test_a_past_due_company_cannot_change_plan(self, on_small, owner, provider, big):
        subs.mark_past_due(on_small.pk)
        assert ask(owner, big).json()["error"]["code"] == "plan_change_unavailable"
        assert provider.calls == []

    def test_an_ended_subscription_cannot_change_plan(self, on_small, owner, provider, big):
        Subscription.objects.filter(company=on_small).update(
            period_end=timezone.now() - timedelta(days=1), renewal=False
        )
        assert ask(owner, big).json()["error"]["code"] == "plan_change_unavailable"

    def test_a_waiting_change_does_not_survive_the_end_of_the_subscription(
        self, on_big, owner, provider, small
    ):
        ask(owner, small)
        subs.cancel(on_big.pk)
        after = current(on_big)
        assert (after.pending_plan, after.pending_change) == (None, "")

    def test_a_waiting_change_survives_a_failed_payment(self, on_big, owner, provider, small):
        ask(owner, small)
        subs.mark_past_due(on_big.pk)
        assert current(on_big).pending_plan == small

    def test_one_company_cannot_touch_another_companys_subscription(
        self, on_big, owner, provider, small, now
    ):
        other = make_company()
        make_company_user(other, role="owner")
        ask(owner, small)
        assert not Subscription.objects.filter(company=other).exclude(pending_change="").exists()


class TestTheProviderClient:
    def call(self, immediate, **fakes):
        plan = SimpleNamespace(pk=7, name="Fake Plan")
        with override_settings(STRIPE_SECRET_KEY=TEST_KEY):
            return stripe_client.change_subscription_price(
                subscription_id=SUB,
                company_id=3,
                plan=plan,
                currency="USD",
                amount_minor=3000,
                immediate=immediate,
                idempotency_key="key-1",
            )

    def patched(self, *, modified):
        retrieved = {"items": {"data": [{"id": "si_1"}]}, "latest_invoice": "in_1"}
        stack = [
            patch.object(stripe.Subscription, "retrieve", return_value=retrieved),
            patch.object(stripe.Price, "create", return_value={"id": "price_1"}),
            patch.object(stripe.Subscription, "modify", return_value=modified)
            if not isinstance(modified, Exception)
            else patch.object(stripe.Subscription, "modify", side_effect=modified),
            patch.object(stripe.Invoice, "retrieve", return_value={"status": "open"}),
            patch.object(stripe.Invoice, "void_invoice"),
        ]
        return stack

    def run(self, immediate, modified):
        from contextlib import ExitStack

        with ExitStack() as stack:
            mocks = [stack.enter_context(each) for each in self.patched(modified=modified)]
            result = self.call(immediate)
        return result, mocks

    def test_an_upgrade_keeps_the_update_pending_until_it_is_paid(self):
        result, mocks = self.run(True, {"pending_update": None})
        sent = mocks[2].call_args.kwargs
        assert sent["proration_behavior"] == "always_invoice"
        assert sent["payment_behavior"] == "pending_if_incomplete"
        assert sent["items"] == [{"id": "si_1", "price": "price_1"}]
        assert result.status == APPLIED

    def test_a_downgrade_has_no_proration_and_no_payment(self):
        result, mocks = self.run(False, {"pending_update": None})
        sent = mocks[2].call_args.kwargs
        assert sent["proration_behavior"] == "none"
        assert "payment_behavior" not in sent
        assert result.status == APPLIED

    def test_the_price_is_monthly_in_usd_and_card_details_are_never_sent(self):
        _, mocks = self.run(True, {"pending_update": None})
        created = mocks[1].call_args.kwargs
        assert (created["currency"], created["unit_amount"], created["recurring"]) == (
            "usd",
            3000,
            {"interval": "month"},
        )
        assert "card" not in json.dumps(
            [mocks[1].call_args.kwargs, mocks[2].call_args.kwargs], default=str
        )

    def test_an_update_the_provider_holds_back_for_a_bank_check_is_reported(self):
        held = {
            "pending_update": {"x": 1},
            "latest_invoice": {
                "payment_intent": {"status": "requires_action"},
                "hosted_invoice_url": "https://pay.example.test/check",
            },
        }
        result, _ = self.run(True, held)
        assert (result.status, result.url) == (NEEDS_ACTION, "https://pay.example.test/check")

    def test_an_update_held_back_by_a_failed_payment_is_declined_and_its_invoice_voided(self):
        held = {
            "pending_update": {"x": 1},
            "latest_invoice": {
                "id": "in_1",
                "payment_intent": {"status": "requires_payment_method"},
            },
        }
        result, mocks = self.run(True, held)
        assert result.status == DECLINED
        mocks[4].assert_called_once()

    def test_a_card_error_is_declined_not_a_crash(self):
        error = stripe.CardError("declined", param=None, code="card_declined")
        with patch.object(
            stripe.Subscription,
            "retrieve",
            return_value={
                "items": {
                    "data": [{"id": "si_1"}],
                },
                "latest_invoice": "in_1",
            },
        ):
            result, _ = self.run(True, error)
        assert result.status == DECLINED

    def test_another_provider_error_becomes_the_plain_message(self):
        with pytest.raises(stripe_client.AppError) as caught:
            self.run(True, stripe.APIConnectionError("secret internals"))
        assert caught.value.code == stripe_client.PROVIDER_CODE
        assert "internals" not in caught.value.message

    def test_a_key_that_is_not_a_test_key_is_refused(self):
        with override_settings(STRIPE_SECRET_KEY="sk_live_x"):  # nosecret: fake
            with pytest.raises(stripe_client.AppError) as caught:
                stripe_client.change_subscription_price(
                    subscription_id=SUB,
                    company_id=1,
                    plan=SimpleNamespace(pk=1, name="x"),
                    currency="USD",
                    amount_minor=1,
                    immediate=True,
                    idempotency_key="k",
                )
        assert caught.value.code == stripe_client.UNAVAILABLE_CODE
