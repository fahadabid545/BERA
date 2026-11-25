from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers.tests.test_admin_roles import client_for as admin_client_for
from audit.models import AuditEvent
from core.errors import AppError
from core.tests.factories import make_admin_user, make_company
from cvs.tests.test_ai_reading import set_setting
from plans import stripe_client
from plans.models import CheckoutAttempt, DiscountCode, PaymentEvent, Subscription
from plans.tests.test_checkout import (
    FakeProvider,
    client_for,
    confirm,
    session_of,
)
from plans.tests.test_regional_pricing import make_plan

pytestmark = pytest.mark.django_db
ADMIN = "/api/admin/discounts/"
CHECK = "/api/company/billing/code/"
START = "/api/company/billing/checkout/"
SAME = "This code cannot be used."


class FakeStripeDiscounts:
    """Stands in for the provider's coupons and promotion codes, and for its checkout (which
    applies the discount to the page's total)."""

    def __init__(self):
        self.coupons, self.promotions, self.calls = {}, {}, []
        self.page = FakeProvider()
        self.unreachable = False

    def create_coupon(self, **sent):
        self.calls.append(("create_coupon", sent))
        coupon = SimpleNamespace(
            id=f"co_{len(self.coupons) + 1}",
            percent_off=sent.get("percent_off"),
            amount_off=sent.get("amount_off_minor"),
            currency="usd" if sent.get("amount_off_minor") else None,
            duration=sent["duration"],
            duration_in_months=sent.get("months"),
            valid=True,
        )
        self.coupons[coupon.id] = coupon
        return coupon

    def create_promotion_code(self, **sent):
        self.calls.append(("create_promotion_code", sent))
        promotion = SimpleNamespace(
            id=f"promo_{len(self.promotions) + 1}",
            code=sent["code"],
            active=True,
            expires_at=int(sent["expires_at"].timestamp()) if sent.get("expires_at") else None,
            max_redemptions=sent.get("max_redemptions"),
            times_redeemed=0,
            restrictions=SimpleNamespace(first_time_transaction=sent["first_time_only"]),
            promotion=SimpleNamespace(coupon=self.coupons[sent["coupon_id"]]),
        )
        self.promotions[promotion.id] = promotion
        return promotion

    def set_promotion_code_active(self, promotion_code_id, active):
        self.calls.append(("active", promotion_code_id, active))
        self.promotions[promotion_code_id].active = active

    def retrieve_promotion_code(self, promotion_code_id):
        if self.unreachable:
            raise AppError("payment_provider_error", "Down.", status_code=502)
        return self.promotions[promotion_code_id]

    def list_promotion_codes(self):
        if self.unreachable:
            raise AppError("payment_provider_error", "Down.", status_code=502)
        return dict(self.promotions)

    def checkout(self, **sent):
        session = self.page.create(**sent)
        promotion = self.promotions.get(sent.get("promotion_code_id"))
        if promotion and not hasattr(session, "discounted"):
            coupon = promotion.promotion.coupon
            full = sent["amount_minor"]
            off = (
                round(full * coupon.percent_off / 100) if coupon.percent_off else coupon.amount_off
            )
            session.amount_total, session.discounted = max(full - off, 0), True
        return session


@pytest.fixture
def fake():
    stripe_fake = FakeStripeDiscounts()
    with (
        patch.object(stripe_client, "create_coupon", stripe_fake.create_coupon),
        patch.object(stripe_client, "create_promotion_code", stripe_fake.create_promotion_code),
        patch.object(
            stripe_client, "set_promotion_code_active", stripe_fake.set_promotion_code_active
        ),
        patch.object(stripe_client, "retrieve_promotion_code", stripe_fake.retrieve_promotion_code),
        patch.object(stripe_client, "list_promotion_codes", stripe_fake.list_promotion_codes),
        patch.object(stripe_client, "create_customer", lambda **sent: "cus_test_1"),
        patch.object(stripe_client, "create_checkout_session", stripe_fake.checkout),
        patch.object(stripe_client, "retrieve_checkout_session", stripe_fake.page.retrieve),
        patch.object(stripe_client, "expire_checkout_session", stripe_fake.page.expire),
    ):
        yield stripe_fake


@pytest.fixture
def boss():
    return admin_client_for(make_admin_user(role="super"))


@pytest.fixture
def plan():
    return make_plan(usd="10.00")


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner(company):
    return client_for(company)


def body(**changes):
    return {"code": "SAVE20", "kind": "percent", "value": 20, "duration": "once", **changes}


def make(boss, **changes):
    response = boss.post(ADMIN, body(**changes), format="json")
    assert response.status_code == 201, response.content
    return DiscountCode.objects.get(code=changes.get("code", "SAVE20").upper())


def check(owner, plan, code="SAVE20"):
    return owner.post(CHECK, {"code": code, "plan_id": plan.pk}, format="json")


def kinds():
    return list(AuditEvent.objects.values_list("kind", flat=True))


class TestMaking:
    def test_a_percent_code_is_made_at_the_provider_and_mirrored_here(self, boss, fake):
        row = make(boss)
        assert (row.stripe_coupon_id, row.stripe_promotion_code_id) == ("co_1", "promo_1")
        coupon_call = fake.calls[0][1]
        assert coupon_call["percent_off"] == 20 and coupon_call["duration"] == "once"
        assert fake.calls[1][1]["code"] == "SAVE20"
        assert "admin.discount_created" in kinds()

    def test_a_fixed_amount_is_sent_in_cents(self, boss, fake):
        make(boss, code="TEN", kind="amount", value="10.50", duration="forever")
        sent = fake.calls[0][1]
        assert sent["amount_off_minor"] == 1050 and sent["percent_off"] is None
        assert sent["duration"] == "forever"

    def test_some_months_needs_the_months(self, boss, fake):
        make(boss, code="THREE", duration="months", months=3)
        assert fake.calls[0][1]["duration"] == "repeating" and fake.calls[0][1]["months"] == 3
        assert (
            boss.post(ADMIN, body(code="NOPE", duration="months"), format="json").status_code == 400
        )

    def test_expiry_use_limit_first_time_and_plan_are_kept(self, boss, fake, plan):
        soon = timezone.now() + timedelta(days=5)
        row = make(
            boss, code="LIMITED", expires_at=soon.isoformat(), max_redemptions=3,
            first_time_only=True, plan_id=plan.pk,
        )  # fmt: skip
        sent = fake.calls[1][1]
        assert sent["max_redemptions"] == 3 and sent["first_time_only"] is True
        assert int(sent["expires_at"].timestamp()) == int(soon.timestamp())
        assert row.plan_id == plan.pk

    @pytest.mark.parametrize(
        "change",
        [
            {"value": 0},
            {"value": 101},
            {"value": "12.5"},
            {"kind": "amount", "value": 0},
            {"kind": "amount", "value": 100000},
            {"duration": "months", "months": 999},
            {"duration": "weekly"},
            {"code": "bad$code"},
            {"code": "ab"},
            {"expires_at": "2020-01-01T00:00:00Z"},
            {"surprise": 1},
        ],
    )
    def test_bad_values_are_refused_and_nothing_is_made(self, boss, fake, change):
        assert boss.post(ADMIN, body(**change), format="json").status_code == 400
        assert fake.calls == [] and not DiscountCode.objects.exists()

    def test_a_code_cannot_be_made_twice(self, boss, fake):
        make(boss)
        assert boss.post(ADMIN, body(code="save20"), format="json").status_code == 400

    def test_the_plan_must_be_an_active_plan(self, boss, fake):
        hidden = make_plan(name="Hidden", status="hidden")
        assert boss.post(ADMIN, body(plan_id=hidden.pk), format="json").status_code == 400

    def test_only_super_admins_may_use_it(self, fake, plan):
        support = admin_client_for(make_admin_user(role="support"))
        assert support.get(ADMIN).status_code == 403
        assert support.post(ADMIN, body(), format="json").status_code == 403
        assert support.patch(f"{ADMIN}1/", {"enabled": False}, format="json").status_code == 403
        assert APIClient().get(ADMIN).status_code == 401
        assert fake.calls == []

    def test_a_provider_failure_makes_no_local_record(self, boss, fake):
        def fail(**sent):
            raise AppError("payment_provider_error", "Down.", status_code=502)

        with patch.object(stripe_client, "create_promotion_code", fail):
            assert boss.post(ADMIN, body(), format="json").status_code == 502
        assert not DiscountCode.objects.exists()


class TestTheList:
    def test_it_shows_the_providers_figures_and_use_counts(self, boss, fake):
        row = make(boss, max_redemptions=5)
        fake.promotions[row.stripe_promotion_code_id].times_redeemed = 2
        item = boss.get(ADMIN).json()["codes"][0]
        assert item["code"] == "SAVE20" and item["percent_off"] == 20
        assert (item["times_redeemed"], item["max_redemptions"]) == (2, 5)
        assert item["duration"] == "once" and item["enabled"] is True

    def test_it_still_lists_when_the_provider_cannot_be_reached(self, boss, fake):
        make(boss)
        fake.unreachable = True
        item = boss.get(ADMIN).json()["codes"][0]
        assert item["code"] == "SAVE20" and item["known"] is False


class TestChanging:
    def test_a_code_is_switched_off_and_on_at_the_provider_and_audited(self, boss, fake):
        row = make(boss)
        url = f"{ADMIN}{row.pk}/"
        assert boss.patch(url, {"enabled": False}, format="json").status_code == 200
        assert fake.promotions["promo_1"].active is False
        row.refresh_from_db()
        assert row.enabled is False
        boss.patch(url, {"enabled": True}, format="json")
        assert kinds().count("admin.discount_changed") == 2
        assert boss.patch(url, {"enabled": True}, format="json").status_code == 400

    def test_it_can_be_limited_to_a_plan_and_freed_again(self, boss, fake, plan):
        row = make(boss)
        url = f"{ADMIN}{row.pk}/"
        assert boss.patch(url, {"plan_id": plan.pk}, format="json").status_code == 200
        row.refresh_from_db()
        assert row.plan_id == plan.pk
        assert boss.patch(url, {"plan_id": None}, format="json").status_code == 200
        row.refresh_from_db()
        assert row.plan_id is None

    def test_an_unknown_code_or_an_empty_change_is_refused(self, boss, fake):
        make(boss)
        assert boss.patch(f"{ADMIN}999/", {"enabled": False}, format="json").status_code == 404
        assert boss.patch(f"{ADMIN}1/", {}, format="json").status_code == 400


class TestCheckingACode:
    def test_the_company_sees_price_discount_and_new_price(self, boss, fake, owner, plan):
        make(boss)
        reply = check(owner, plan)
        assert reply.status_code == 200, reply.content
        assert reply.json() == {
            "kind": "coupon", "plan_id": plan.pk, "currency": "USD", "price": "10.00",
            "discount": "2.00", "new_price": "8.00", "duration": "once", "months": None,
        }  # fmt: skip

    def test_a_fixed_amount_never_takes_the_price_below_zero(self, boss, fake, owner, plan):
        make(boss, code="BIG", kind="amount", value=50, duration="forever")
        reply = check(owner, plan, "big").json()
        assert (reply["discount"], reply["new_price"], reply["duration"]) == (
            "10.00",
            "0.00",
            "forever",
        )

    def test_a_months_discount_says_how_long(self, boss, fake, owner, plan):
        make(boss, code="THREE", duration="months", months=3)
        assert check(owner, plan, "three").json()["months"] == 3

    def test_every_kind_of_unusable_code_gets_the_same_answer(
        self, boss, fake, owner, plan, company
    ):
        other_plan = make_plan(name="Other", usd="20.00")
        make(boss, code="WRONGPLAN", plan_id=other_plan.pk)
        off = make(boss, code="OFF")
        boss.patch(f"{ADMIN}{off.pk}/", {"enabled": False}, format="json")
        expired = make(boss, code="EXPIRED")
        fake.promotions[expired.stripe_promotion_code_id].expires_at = int(
            (timezone.now() - timedelta(days=1)).timestamp()
        )
        used = make(boss, code="USEDUP", max_redemptions=1)
        fake.promotions[used.stripe_promotion_code_id].times_redeemed = 1
        invalid = make(boss, code="INVALID")
        fake.coupons[invalid.stripe_coupon_id].valid = False
        first = make(boss, code="FIRSTONLY", first_time_only=True)
        PaymentEvent.objects.create(
            company=company, provider_event_id="evt_1", kind="payment", amount_minor=1000,
            currency="USD", occurred_at=timezone.now(),
        )  # fmt: skip
        assert first.pk
        answers = {
            check(owner, plan, code).content
            for code in ("WRONGPLAN", "OFF", "EXPIRED", "USEDUP", "INVALID", "FIRSTONLY", "NOSUCH")
        }
        assert len(answers) == 1
        assert SAME.encode() in answers.pop()

    def test_a_first_time_code_works_for_a_company_that_never_paid(self, boss, fake, owner, plan):
        make(boss, first_time_only=True)
        assert check(owner, plan).status_code == 200

    def test_a_plan_limited_code_works_for_its_plan(self, boss, fake, owner, plan):
        make(boss, plan_id=plan.pk)
        assert check(owner, plan).status_code == 200

    def test_tries_are_limited_per_company(self, boss, fake, owner, plan):
        set_setting("rate_limits.code_attempts_per_hour", 2)
        statuses = [check(owner, plan, f"NOPE{n}").status_code for n in range(3)]
        assert statuses == [400, 400, 429]
        make(boss)
        assert check(owner, plan).status_code == 429

    def test_only_the_owner_may_check(self, boss, fake, company, plan):
        member = client_for(company, role="member")
        make(boss)
        assert check(member, plan).status_code == 403
        assert check(APIClient(), plan).status_code == 401

    def test_without_a_plan_it_only_says_the_code_is_good(self, boss, fake, owner, plan):
        make(boss, plan_id=plan.pk)
        reply = owner.post(CHECK, {"code": "SAVE20"}, format="json")
        assert reply.status_code == 200 and reply.json() == {"kind": "coupon"}
        assert owner.post(CHECK, {"code": "NOSUCH"}, format="json").status_code == 400

    def test_a_trial_code_is_recognised_in_the_same_field(self, boss, fake, owner, plan):
        from django.utils import timezone as tz

        from plans import trials

        row, code = trials.create_code(
            make_admin_user(role="super"), name="Fake", plan=plan, days=7, cv_limit=20,
            expires_at=tz.now() + timedelta(days=3),
        )  # fmt: skip
        reply = owner.post(CHECK, {"code": code}, format="json")
        assert reply.json() == {"kind": "trial", "plan": plan.name, "days": 7, "cv_limit": 20}
        row.refresh_from_db()
        assert row.redeemed_at is None  # checking changes nothing

    def test_an_unknown_plan_gets_the_same_answer(self, boss, fake, owner):
        make(boss)
        reply = owner.post(CHECK, {"code": "SAVE20", "plan_id": 99999}, format="json")
        assert reply.status_code == 400 and SAME.encode() in reply.content


class TestCheckout:
    def start(self, owner, plan, code=None):
        sent = {"plan_id": plan.pk, **({"code": code} if code else {})}
        return owner.post(START, sent, format="json")

    def test_the_code_is_passed_to_the_page_and_the_price_after_the_discount_is_kept(
        self, boss, fake, owner, plan, company
    ):
        make(boss)
        assert self.start(owner, plan, "save20").status_code == 200
        sent = fake.page.created[0]
        assert sent["promotion_code_id"] == "promo_1" and sent["amount_minor"] == 1000
        attempt = CheckoutAttempt.objects.get(company=company)
        assert attempt.promotion_code_id == "promo_1" and attempt.discounted_minor == 800

    def test_without_a_code_nothing_changes(self, fake, owner, plan, company):
        assert self.start(owner, plan).status_code == 200
        attempt = CheckoutAttempt.objects.get(company=company)
        assert attempt.promotion_code_id == "" and attempt.discounted_minor is None
        assert fake.page.created[0]["promotion_code_id"] is None

    def test_a_paid_page_is_accepted_at_the_discounted_price(
        self, boss, fake, owner, plan, company
    ):
        make(boss)
        self.start(owner, plan, "SAVE20")
        fake.page.pay(session_of(company))
        assert confirm(owner, session_of(company)).json() == {"result": "activated"}
        assert Subscription.objects.get(company=company).state == "active"

    def test_a_paid_page_with_another_amount_is_refused(self, boss, fake, owner, plan, company):
        make(boss)
        self.start(owner, plan, "SAVE20")
        session = fake.page.retrieve(session_of(company))
        session.amount_total = 100  # not what the provider said the page charges
        fake.page.pay(session.id)
        assert confirm(owner, session.id).status_code == 409
        assert Subscription.objects.get(company=company).state != "active"

    def test_a_paid_page_without_a_discount_still_has_to_pay_the_list_price(
        self, fake, owner, plan, company
    ):
        self.start(owner, plan)
        fake.page.retrieve(session_of(company)).amount_total = 800
        fake.page.pay(session_of(company))
        assert confirm(owner, session_of(company)).status_code == 409

    def test_a_double_click_with_the_same_code_reuses_the_page(self, boss, fake, owner, plan):
        make(boss)
        first = self.start(owner, plan, "SAVE20").json()["url"]
        assert self.start(owner, plan, "SAVE20").json()["url"] == first
        assert len(fake.page.created) == 1

    def test_another_code_or_none_makes_a_new_page(self, boss, fake, owner, plan):
        make(boss)
        make(boss, code="OTHER", value=50)
        first = self.start(owner, plan, "SAVE20").json()["url"]
        assert self.start(owner, plan, "OTHER").json()["url"] != first
        assert len(fake.page.created) == 2

    def test_an_unusable_code_stops_checkout_before_any_page_is_made(
        self, fake, owner, plan, company
    ):
        reply = self.start(owner, plan, "NOSUCH")
        assert reply.status_code == 400 and SAME.encode() in reply.content
        assert (
            fake.page.created == [] and not CheckoutAttempt.objects.filter(company=company).exists()
        )

    def test_a_code_limited_to_another_plan_stops_checkout(self, boss, fake, owner, plan):
        other = make_plan(name="Other", usd="20.00")
        make(boss, plan_id=other.pk)
        assert self.start(owner, plan, "SAVE20").status_code == 400
        assert fake.page.created == []

    def test_tries_through_checkout_count_too(self, fake, owner, plan):
        set_setting("rate_limits.code_attempts_per_hour", 2)
        assert [self.start(owner, plan, f"NOPE{n}").status_code for n in range(3)] == [
            400,
            400,
            429,
        ]

    def test_the_provider_refusing_the_code_gives_the_same_answer(self, boss, fake, owner, plan):
        make(boss)

        def refuse(**sent):
            raise AppError("code_not_usable", SAME, status_code=400)

        with patch.object(stripe_client, "create_checkout_session", refuse):
            reply = self.start(owner, plan, "SAVE20")
        assert reply.status_code == 400 and SAME.encode() in reply.content

    def test_change_plan_does_not_take_a_code(self, fake, owner, plan):
        reply = owner.post(
            "/api/company/billing/change-plan/", {"plan_id": plan.pk, "code": "X"}, format="json"
        )
        assert reply.status_code == 400


class TestTheClientCallsTheProviderCorrectly:
    def test_the_discount_goes_in_and_the_providers_code_field_stays_off(self):
        sent = {}

        def fake_create(**kwargs):
            sent.update(kwargs)
            return SimpleNamespace(id="cs_1")

        plan = make_plan()
        with (
            patch.object(stripe.checkout.Session, "create", fake_create),
            patch.object(stripe_client, "_key", lambda: "sk_test_fake"),
        ):
            stripe_client.create_checkout_session(
                idempotency_key="k", company_id=1, customer_id="cus", plan=plan, currency="USD",
                amount_minor=1000, expires_at=timezone.now(), success_url="https://x.test/a",
                cancel_url="https://x.test/b", promotion_code_id="promo_1",
            )  # fmt: skip
            assert sent["discounts"] == [{"promotion_code": "promo_1"}]
            assert "allow_promotion_codes" not in sent
            sent.clear()
            stripe_client.create_checkout_session(
                idempotency_key="k", company_id=1, customer_id="cus", plan=plan, currency="USD",
                amount_minor=1000, expires_at=timezone.now(), success_url="https://x.test/a",
                cancel_url="https://x.test/b",
            )  # fmt: skip
            assert "discounts" not in sent and "allow_promotion_codes" not in sent

    def test_a_refused_code_at_the_provider_is_the_same_plain_answer(self):
        def refuse(**kwargs):
            raise stripe.InvalidRequestError("secret internals", param="discounts")

        with (
            patch.object(stripe.checkout.Session, "create", refuse),
            patch.object(stripe_client, "_key", lambda: "sk_test_fake"),
            pytest.raises(AppError) as caught,
        ):
            stripe_client.create_checkout_session(
                idempotency_key="k", company_id=1, customer_id="cus", plan=make_plan(),
                currency="USD",
                amount_minor=1000, expires_at=timezone.now(), success_url="https://x.test/a",
                cancel_url="https://x.test/b", promotion_code_id="promo_1",
            )  # fmt: skip
        assert caught.value.code == "code_not_usable" and "internals" not in caught.value.message


class TestRevenue:
    def test_a_discounted_payment_shows_at_the_amount_really_paid(self, company, plan):
        from datetime import date

        from plans import revenue

        PaymentEvent.objects.create(
            company=company, provider_event_id="evt_d", kind="payment", amount_minor=800,
            currency="USD", occurred_at=timezone.now(), plan=plan,
        )  # fmt: skip
        today = date.today()
        total = revenue.received_total(today - timedelta(days=1), today + timedelta(days=1))
        assert str(total) == "8"

    def test_a_trial_company_with_nothing_paid_is_a_plain_free_row_not_a_loss(self, company, plan):
        from plans import subscriptions

        subscriptions.start_trial(
            company.pk, plan, period_end=timezone.now() + timedelta(days=5), cv_limit=5,
            source="admin",
        )  # fmt: skip
        from adminusers.profitability import _row

        row, paid, _cost = _row(company, subscriptions.get_subscription(company.pk), 3, 0)
        assert row["subscription_state"] == "granted_free"
        assert (
            row["paid_usd"] == "0.00" and row["margin_percent"] is None and row["flagged"] is False
        )
