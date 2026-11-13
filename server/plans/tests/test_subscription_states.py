from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from audit.models import AuditEvent
from core.errors import AppError
from core.tests.factories import make_admin_user, make_company, make_company_user
from emailing.models import OutgoingEmail
from plans import subscriptions as subs
from plans.models import PendingPlanChange, Plan, Subscription
from plans.service import update_plan
from plans.subscribers import subscriber_count
from platform_settings.service import get_setting

pytestmark = pytest.mark.django_db
State = Subscription.State
DAY = timedelta(days=1)


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


def paid(company, plan, *, days=30, renewal=True):
    now = timezone.now()
    return subs.activate(
        company.pk, plan, period_start=now, period_end=now + days * DAY, renewal=renewal
    )


def state(company):
    return subs.effective_state(subs.get_subscription(company.pk))


def full_access(company):
    return [
        subs.can_create_project(company.pk),
        subs.can_upload(company.pk),
        subs.can_score(company.pk),
    ]


def log_kinds(company):
    return list(AuditEvent.objects.filter(company_id=company.pk).values_list("kind", flat=True))


class TestNoPlan:
    def test_a_new_company_has_no_plan(self, company):
        assert state(company) == State.NO_PLAN

    def test_it_can_view_but_not_create_upload_or_score(self, company):
        assert subs.can_view(company.pk)
        assert full_access(company) == [False, False, False]

    def test_a_company_has_exactly_one_subscription(self, company):
        subs.get_subscription(company.pk)
        subs.get_subscription(company.pk)
        assert Subscription.objects.filter(company=company).count() == 1


class TestActive:
    def test_paying_gives_full_access_and_holds_the_plan(self, company, plan):
        paid(company, plan)
        subscription = subs.get_subscription(company.pk)
        assert (subscription.state, subscription.plan, subscription.renewal) == (
            State.ACTIVE,
            plan,
            True,
        )
        assert full_access(company) == [True, True, True]

    def test_paying_again_replaces_the_period_and_never_adds_a_second_subscription(
        self, company, plan
    ):
        paid(company, plan)
        paid(company, plan, days=60)
        assert Subscription.objects.filter(company=company).count() == 1

    def test_a_renewing_period_that_ran_out_waits_for_the_payment_event(self, company, plan):
        paid(company, plan)
        later = timezone.now() + 40 * DAY
        assert subs.effective_state(subs.get_subscription(company.pk), later) == State.ACTIVE

    def test_a_period_without_renewal_expires_when_it_ends(self, company, plan):
        paid(company, plan, renewal=False)
        subscription = subs.get_subscription(company.pk)
        assert subs.effective_state(subscription, timezone.now() + 29 * DAY) == State.ACTIVE
        assert subs.effective_state(subscription, timezone.now() + 31 * DAY) == State.EXPIRED

    def test_paying_applies_a_price_change_that_was_waiting(self, company, plan):
        admin = make_admin_user(role="super")
        paid(company, plan)
        update_plan(admin, plan.pk, {"cvs_per_month": 200}, reason="Fake reason.")
        assert PendingPlanChange.objects.filter(plan=plan).exists()
        paid(company, plan)
        plan.refresh_from_db()
        assert plan.cvs_per_month == 200
        assert not PendingPlanChange.objects.filter(plan=plan).exists()


class TestPastDue:
    def test_full_access_during_the_grace_period_with_a_warning(self, company, plan):
        paid(company, plan)
        subs.mark_past_due(company.pk)
        assert state(company) == State.PAST_DUE
        assert full_access(company) == [True, True, True]
        status = subs.status_of(company.pk)
        assert status["grace_ends_at"] is not None

    def test_it_expires_after_the_grace_days_from_the_platform_setting(self, company, plan):
        paid(company, plan)
        subs.mark_past_due(company.pk)
        subscription = subs.get_subscription(company.pk)
        grace = timedelta(days=get_setting("billing.past_due_grace_days"))
        start = subscription.past_due_since
        assert subs.effective_state(subscription, start + grace - timedelta(minutes=1)) == (
            State.PAST_DUE
        )
        assert subs.effective_state(subscription, start + grace) == State.EXPIRED

    def test_only_an_active_subscription_can_become_past_due(self, company, plan):
        with pytest.raises(AppError):
            subs.mark_past_due(company.pk)
        paid(company, plan)
        subs.mark_past_due(company.pk)
        with pytest.raises(AppError):
            subs.mark_past_due(company.pk)

    def test_paying_again_restores_active(self, company, plan):
        paid(company, plan)
        subs.mark_past_due(company.pk)
        paid(company, plan)
        subscription = subs.get_subscription(company.pk)
        assert (subscription.state, subscription.past_due_since) == (State.ACTIVE, None)


class TestCancelled:
    def test_access_continues_until_the_period_ends_and_renewal_is_off(self, company, plan):
        paid(company, plan)
        subs.cancel(company.pk)
        subscription = subs.get_subscription(company.pk)
        assert (subscription.state, subscription.renewal) == (State.CANCELLED, False)
        assert full_access(company) == [True, True, True]
        assert subs.effective_state(subscription, timezone.now() + 31 * DAY) == State.EXPIRED

    def test_only_an_active_subscription_can_be_cancelled(self, company):
        with pytest.raises(AppError):
            subs.cancel(company.pk)


class TestExpired:
    def test_view_and_download_only(self, company, plan):
        paid(company, plan)
        subs.expire(company.pk)
        assert state(company) == State.EXPIRED
        assert subs.can_view(company.pk)
        assert full_access(company) == [False, False, False]

    def test_an_expired_subscription_cannot_expire_again(self, company, plan):
        paid(company, plan)
        subs.expire(company.pk)
        with pytest.raises(AppError):
            subs.expire(company.pk)

    def test_paying_brings_an_expired_company_back(self, company, plan):
        paid(company, plan)
        subs.expire(company.pk)
        paid(company, plan)
        assert state(company) == State.ACTIVE


class TestGrantedFree:
    def grant(self, company, plan, days=30):
        admin = make_admin_user(role="super")
        subs.grant_free(
            company.pk, plan, period_end=timezone.now() + days * DAY, by=admin, reason="Fake."
        )
        return admin

    def test_full_access_for_the_chosen_period_then_expired(self, company, plan):
        self.grant(company, plan)
        subscription = subs.get_subscription(company.pk)
        assert full_access(company) == [True, True, True]
        assert subs.effective_state(subscription, timezone.now() + 31 * DAY) == State.EXPIRED

    def test_a_reason_is_required(self, company, plan):
        admin = make_admin_user(role="super")
        with pytest.raises(AppError) as error:
            subs.grant_free(company.pk, plan, period_end=timezone.now() + DAY, by=admin, reason=" ")
        assert error.value.code == "reason_required"
        assert state(company) == State.NO_PLAN

    def test_the_period_must_end_in_the_future(self, company, plan):
        admin = make_admin_user(role="super")
        with pytest.raises(AppError):
            subs.grant_free(
                company.pk, plan, period_end=timezone.now() - DAY, by=admin, reason="Fake."
            )

    @pytest.mark.parametrize("make_paid", [True])
    def test_it_is_refused_while_a_subscription_still_gives_access(self, company, plan, make_paid):
        paid(company, plan)
        with pytest.raises(AppError):
            self.grant(company, plan)
        assert state(company) == State.ACTIVE

    def test_it_is_refused_while_another_free_grant_runs(self, company, plan):
        self.grant(company, plan)
        with pytest.raises(AppError):
            self.grant(company, plan)

    def test_it_can_be_given_after_expiry(self, company, plan):
        paid(company, plan)
        subs.expire(company.pk)
        self.grant(company, plan)
        assert state(company) == State.GRANTED_FREE

    def test_it_can_be_ended_early(self, company, plan):
        admin = self.grant(company, plan)
        subs.end_free(company.pk, by=admin, reason="Fake reason.")
        assert state(company) == State.EXPIRED
        assert full_access(company) == [False, False, False]

    def test_ending_early_needs_a_reason_and_a_free_grant(self, company, plan):
        admin = make_admin_user(role="super")
        with pytest.raises(AppError):
            subs.end_free(company.pk, by=admin, reason="Fake.")
        self.grant(company, plan)
        with pytest.raises(AppError) as error:
            subs.end_free(company.pk, by=admin, reason="")
        assert error.value.code == "reason_required"
        assert state(company) == State.GRANTED_FREE


class TestLogAndEmail:
    def test_every_change_is_logged_with_old_and_new_state(self, company, plan):
        paid(company, plan)
        subs.mark_past_due(company.pk)
        events = AuditEvent.objects.filter(
            company_id=company.pk, kind="subscription.state_changed"
        ).order_by("id")
        assert [e.details["changes"]["state"] for e in events] == [
            {"old": "no_plan", "new": "active"},
            {"old": "active", "new": "past_due"},
        ]
        assert events[0].details["source"] == "payment"

    def test_a_free_grant_is_logged_by_the_admin_with_the_reason(self, company, plan):
        admin = make_admin_user(role="super")
        subs.grant_free(
            company.pk, plan, period_end=timezone.now() + DAY, by=admin, reason="Fake reason."
        )
        event = AuditEvent.objects.get(kind="admin.free_subscription_granted")
        assert (event.actor_id, event.reason) == (admin.pk, "Fake reason.")

    def test_a_refused_change_leaves_no_log_and_no_email(self, company):
        with pytest.raises(AppError):
            subs.cancel(company.pk)
        assert log_kinds(company) == []
        assert OutgoingEmail.objects.count() == 0

    def test_the_owner_is_emailed_for_each_state(self, company, plan):
        owner = company.users.get(role="owner")
        paid(company, plan)
        subs.mark_past_due(company.pk)
        subs.expire(company.pk)
        emails = [e for e in OutgoingEmail.objects.all() if e.to_address == owner.email]
        assert len(emails) == 3
        assert {e.template for e in emails} == {"usage_notice"}

    def test_members_are_not_emailed(self, company, plan):
        member = make_company_user(company, role="member")
        paid(company, plan)
        assert all(e.to_address != member.email for e in OutgoingEmail.objects.all())

    def test_no_secrets_or_card_data_are_logged(self, company, plan):
        paid(company, plan)
        event = AuditEvent.objects.get(kind="subscription.state_changed")
        assert set(event.details) == {"source", "changes"}


class TestTheJob:
    def test_it_saves_the_changes_the_dates_imply(self, company, plan):
        paid(company, plan, renewal=False)
        Subscription.objects.filter(company=company).update(period_end=timezone.now() - DAY)
        other = make_company()
        make_company_user(other, role="owner")
        paid(other, plan)
        assert subs.expire_lapsed_subscriptions() == 1
        assert subs.get_subscription(company.pk).state == State.EXPIRED
        assert subs.get_subscription(other.pk).state == State.ACTIVE

    def test_a_lapsed_grace_period_is_saved_logged_and_emailed(self, company, plan):
        paid(company, plan)
        subs.mark_past_due(company.pk)
        Subscription.objects.filter(company=company).update(
            past_due_since=timezone.now() - 30 * DAY
        )
        before = OutgoingEmail.objects.count()
        subs.expire_lapsed_subscriptions()
        assert OutgoingEmail.objects.count() == before + 1
        assert log_kinds(company)[-1] == "subscription.state_changed"

    def test_running_it_twice_changes_nothing_more(self, company, plan):
        paid(company, plan, renewal=False)
        Subscription.objects.filter(company=company).update(period_end=timezone.now() - DAY)
        assert subs.expire_lapsed_subscriptions() == 1
        assert subs.expire_lapsed_subscriptions() == 0


class TestSubscribers:
    def test_companies_with_access_count_as_subscribers(self, company, plan):
        paid(company, plan)
        assert subscriber_count(plan) == 1

    def test_expired_and_plan_less_companies_do_not(self, company, plan):
        paid(company, plan)
        subs.expire(company.pk)
        assert subscriber_count(plan) == 0

    def test_a_plan_with_subscribers_cannot_be_deleted(self, company, plan):
        from plans.service import delete_plan

        paid(company, plan)
        with pytest.raises(AppError) as error:
            delete_plan(make_admin_user(role="super"), plan.pk, reason="Fake.")
        assert error.value.status_code == 409


class TestCompaniesAreSeparate:
    def test_one_companys_subscription_never_shows_or_changes_anothers(self, company, plan):
        other = make_company()
        paid(company, plan)
        assert subs.status_of(other.pk)["state"] == State.NO_PLAN
        assert subs.can_upload(other.pk) is False
        subs.expire(company.pk)
        paid(other, plan)
        assert subs.get_subscription(company.pk).state == State.EXPIRED
        assert subs.get_subscription(other.pk).state == State.ACTIVE
        assert Subscription.objects.filter(company=company).count() == 1


class TestCompaniesCannotChangeTheirState:
    def test_no_route_reaches_the_subscription(self):
        from django.urls import get_resolver

        from core.tests.test_route_protection import all_routes

        names = [route for route, _ in all_routes(get_resolver().url_patterns)]
        # Only the admin controls (super admin, with a reason) can reach a subscription.
        assert all(r.startswith("api/admin/") for r in names if "subscription" in r)
