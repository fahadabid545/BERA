import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from activity import service as activity
from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import make_plan
from feedback.models import Feedback
from freeaccess import service
from freeaccess.models import FreeAccess, FreeAccessInvite
from freeaccess.tests.test_free_access import ADMIN, Org, beta_code, beta_email, grants_of
from plans import subscriptions
from plans.models import Plan
from usage import service as usage

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss():
    return admin_client("super")[0]


@pytest.fixture
def admin():
    return admin_client("super")[1]


@pytest.fixture
def smallest_plan():
    return make_plan(name="Small", price_usd=10)


def one_beta(admin):
    org = Org()
    beta_email(admin, org)
    return org, grants_of(org).get()


def pay(org, plan, name="Paid Ltd"):
    org.company.name = name
    org.company.save()
    now = timezone.now()
    subscriptions.activate(
        org.id,
        plan,
        period_start=now,
        period_end=now + timedelta(days=30),
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
    )


class TestDetail:
    def test_it_shows_usage_daily_cvs_activity_and_feedback_of_the_company(
        self, boss, admin, smallest_plan
    ):
        org, grant = one_beta(admin)
        for _ in range(2):
            cv = uuid.uuid4()
            usage.accept_cv(org.id, cv)
            usage.mark_scored(org.id, cv)
        activity.record("download", company_id=org.id, actor=org.owner)
        Feedback.objects.create(
            company_id=org.id, user=org.owner, kind="idea", message="Add dark mode", page="/x"
        )
        body = boss.get(f"{ADMIN}access/{grant.pk}/").json()
        assert body["usage"]["cvs_today"] == 2
        assert body["usage"]["cvs_per_day_limit"] == 5
        assert body["daily_cvs"][-1]["cvs"] == 2 and len(body["daily_cvs"]) == 14
        assert [item["kind"] for item in body["activity"]] == ["download"]
        assert body["feedback"][0]["message"] == "Add dark mode"
        assert body["status"] == "active" and body["company"]["id"] == str(org.id)

    def test_another_company_never_appears_in_it(self, boss, admin, smallest_plan):
        org, grant = one_beta(admin)
        other = Org()
        activity.record("download", company_id=other.id, actor=other.owner)
        Feedback.objects.create(
            company_id=other.id, user=other.owner, kind="bug", message="Other", page="/x"
        )
        cv = uuid.uuid4()
        usage.accept_cv(other.id, cv)
        body = boss.get(f"{ADMIN}access/{grant.pk}/").json()
        assert body["activity"] == [] and body["feedback"] == []
        assert body["usage"]["cvs_today"] == 0

    def test_a_missing_access_is_not_found_and_support_cannot_read_it(self, boss, admin):
        assert boss.get(f"{ADMIN}access/{uuid.uuid4()}/").status_code == 404
        support = admin_client("support")[0]
        assert support.get(f"{ADMIN}access/{uuid.uuid4()}/").status_code == 403

    def test_the_number_of_days_and_items_are_settings(self, boss, admin, smallest_plan):
        _, grant = one_beta(admin)
        set_setting("free_access.chart_days", 7)
        assert len(boss.get(f"{ADMIN}access/{grant.pk}/").json()["daily_cvs"]) == 7


class TestOverview:
    def test_it_counts_each_state_and_sums_only_beta_companies(self, boss, admin, smallest_plan):
        org, grant = one_beta(admin)
        revoked_org = Org()
        beta_email(admin, revoked_org)
        service.revoke(admin, grants_of(revoked_org).get().pk)
        cv = uuid.uuid4()
        usage.accept_cv(org.id, cv)
        outsider = Org()
        usage.accept_cv(outsider.id, uuid.uuid4())
        body = boss.get(f"{ADMIN}overview/").json()
        assert (body["active"], body["ended"], body["revoked"]) == (1, 0, 1)
        assert sum(day["cvs"] for day in body["daily_cvs"]) == 1

    def test_it_counts_the_feedback_of_beta_companies_only(self, boss, admin, smallest_plan):
        org, _ = one_beta(admin)
        Feedback.objects.create(
            company_id=org.id, user=org.owner, kind="bug", message="a", page="/"
        )
        other = Org()
        Feedback.objects.create(
            company_id=other.id, user=other.owner, kind="bug", message="b", page="/"
        )
        assert boss.get(f"{ADMIN}overview/").json()["feedback"] == 1


class TestPaidList:
    def test_only_card_paying_companies_are_listed_with_their_other_access(
        self, boss, admin, smallest_plan
    ):
        paying = Org()
        pay(paying, smallest_plan)
        beta_email(admin, paying)  # also a beta user: revoking it never touches the plan
        trial_only = Org()
        beta_email(admin, trial_only)
        subscriptions.activate(
            Org().id,
            smallest_plan,
            period_start=timezone.now(),
            period_end=timezone.now() + timedelta(days=30),
        )  # no card ids: not a paying company
        body = boss.get(f"{ADMIN}paid/").json()
        assert body["total"] == 1
        row = body["items"][0]
        assert row["id"] == str(paying.id) and row["plan_name"] == "Small"
        assert row["also_free_access"] == ["beta"]

    def test_it_is_paged_and_searchable(self, boss, smallest_plan):
        set_setting("free_access.page_size", 5)
        for index in range(6):
            pay(Org(), smallest_plan, name=f"Firm {index}")
        first = boss.get(f"{ADMIN}paid/").json()
        second = boss.get(f"{ADMIN}paid/?page=2").json()
        assert first["total"] == 6 and len(first["items"]) == 5 and len(second["items"]) == 1
        found = boss.get(f"{ADMIN}paid/?search=firm 3").json()
        assert [row["name"] for row in found["items"]] == ["Firm 3"]
        assert boss.get(f"{ADMIN}paid/?page=abc").json()["page"] == 1

    def test_only_a_super_admin_reads_it(self, smallest_plan):
        assert admin_client("support")[0].get(f"{ADMIN}paid/").status_code == 403


class TestChangesFromTheTab:
    def test_a_permitted_access_can_be_given_another_plan(self, boss, admin, smallest_plan):
        bigger = make_plan(name="Bigger", price_usd=50)
        org = Org()
        service.invite_email(
            admin, kind="permitted_email", email=org.owner.email, plan_id=smallest_plan.pk
        )
        grant = grants_of(org).get()
        response = boss.patch(f"{ADMIN}access/{grant.pk}/", {"plan_id": bigger.pk}, format="json")
        assert response.status_code == 200 and response.json()["plan"]["name"] == "Bigger"
        assert AuditEvent.objects.filter(kind="admin.free_access_plan_changed").exists()
        assert "Bigger" not in str(list(AuditEvent.objects.values()))

    def test_a_beta_access_has_no_plan_to_change_and_an_unknown_plan_is_refused(
        self, boss, admin, smallest_plan
    ):
        _, grant = one_beta(admin)
        assert (
            boss.patch(
                f"{ADMIN}access/{grant.pk}/", {"plan_id": smallest_plan.pk}, format="json"
            ).status_code
            == 400
        )
        org = Org()
        service.invite_email(
            admin, kind="permitted_email", email=org.owner.email, plan_id=smallest_plan.pk
        )
        permitted = grants_of(org).get()
        Plan.objects.filter(pk=smallest_plan.pk).update(status="archived")
        assert (
            boss.patch(
                f"{ADMIN}access/{permitted.pk}/", {"plan_id": smallest_plan.pk}, format="json"
            ).status_code
            == 400
        )

    def test_an_unused_invite_can_be_deleted_and_a_used_one_cannot(
        self, boss, admin, smallest_plan
    ):
        unused, _ = beta_code(admin, label="Spare")
        assert boss.delete(f"{ADMIN}invites/{unused.pk}/").status_code == 204
        assert not FreeAccessInvite.objects.filter(pk=unused.pk).exists()
        used, code = beta_code(admin, label="Used")
        Org().client.post("/api/company/billing/beta/redeem/", {"code": code}, format="json")
        assert boss.delete(f"{ADMIN}invites/{used.pk}/").status_code == 409
        assert FreeAccessInvite.objects.filter(pk=used.pk).exists()
        assert FreeAccess.objects.count() == 1

    def test_support_cannot_change_or_delete_anything(self, admin, smallest_plan):
        support = admin_client("support")[0]
        invite, _ = beta_code(admin)
        assert support.delete(f"{ADMIN}invites/{invite.pk}/").status_code == 403
        assert (
            support.patch(
                f"{ADMIN}access/{uuid.uuid4()}/", {"plan_id": 1}, format="json"
            ).status_code
            == 403
        )

    def test_the_beta_settings_page_lists_only_beta_values(self, boss):
        keys = [item["key"] for item in boss.get("/api/admin/settings/?page=beta").json()["items"]]
        assert "beta.cvs_per_day" in keys and all(key.startswith("beta.") for key in keys)
