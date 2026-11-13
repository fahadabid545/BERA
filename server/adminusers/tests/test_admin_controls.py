import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers.models import AdminUser
from audit.models import AuditEvent
from companies.models import Company, CompanyUser
from core.tests.factories import make_admin_user, make_company, make_company_user
from emailing.models import OutgoingEmail
from plans import limits
from plans import subscriptions as subs
from plans.models import LimitOverride, Plan
from signin import service as signin
from signin.models import Session
from twostep.models import RecoveryCode
from usage import service as usage

pytestmark = pytest.mark.django_db
REASON = "Fake reason for the test."
DAY = timedelta(days=1)


def client_for(admin):
    issued = signin.start_session(user_id=admin.pk, role=admin.role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def boss():
    admin = make_admin_user(role="super")
    return admin, client_for(admin)


@pytest.fixture
def company():
    company = make_company()
    make_company_user(company, role="owner", email_verified=True)
    return company


@pytest.fixture
def plan():
    return Plan.objects.create(
        name="Fake Plan",
        status="active",
        price_usd=Decimal("10"),
        cvs_per_month=5,
        cvs_per_project=3,
        max_projects=2,
        max_team_accounts=2,
        max_top_n=10,
        monthly_ai_token_cap=1000,
    )


def owner_emails(company):
    owner = company.users.get(role="owner")
    return [e for e in OutgoingEmail.objects.all() if e.to_address == owner.email]


def company_session(person):
    return signin.start_session(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind="company"
    )


def live_sessions(person, kind="company"):
    return Session.objects.filter(user_id=person.pk, kind=kind, status="active").count()


def last_event(kind):
    return AuditEvent.objects.filter(kind=kind).order_by("-id").first()


def post(client, path, **body):
    return client.post(path, body, format="json")


class TestEveryActionNeedsAReasonAndASuperAdmin:
    PATHS = [
        ("post", "suspend/"),
        ("post", "unsuspend/"),
        ("put", "limits/cvs_per_month/"),
        ("delete", "limits/cvs_per_month/"),
        ("post", "subscription/grant-free/"),
        ("post", "subscription/end-free/"),
        ("post", "subscription/terminate/"),
    ]

    @pytest.mark.parametrize(("method", "tail"), PATHS)
    def test_a_missing_or_blank_reason_is_refused_and_changes_nothing(
        self, boss, company, method, tail
    ):
        _, client = boss
        url = f"/api/admin/companies/{company.pk}/{tail}"
        extra = {"value": 7, "plan_id": 1, "period_end": "2099-01-01T00:00:00Z"}
        for body in ({**extra}, {**extra, "reason": "   "}):
            response = getattr(client, method)(url, body, format="json")
            assert response.status_code == 400, response.content
        assert not AuditEvent.objects.filter(kind__startswith="admin.").exists()
        assert owner_emails(company) == []

    @pytest.mark.parametrize(("method", "tail"), PATHS)
    def test_support_is_refused(self, company, method, tail):
        support = make_admin_user(role="support")
        url = f"/api/admin/companies/{company.pk}/{tail}"
        response = getattr(client_for(support), method)(url, {"reason": REASON}, format="json")
        assert response.status_code == 403
        assert company.status == "active"

    @pytest.mark.parametrize(("method", "tail"), PATHS)
    def test_visitors_and_company_sign_ins_are_refused(self, company, method, tail):
        url = f"/api/admin/companies/{company.pk}/{tail}"
        assert getattr(APIClient(), method)(url, {}, format="json").status_code == 401
        owner = company.users.get(role="owner")
        issued = company_session(owner)
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert getattr(client, method)(url, {"reason": REASON}, format="json").status_code == 401

    def test_an_unknown_company_is_not_found(self, boss):
        _, client = boss
        assert (
            post(client, "/api/admin/companies/999999/suspend/", reason=REASON).status_code == 404
        )


class TestSuspending:
    def test_it_suspends_ends_every_session_and_emails_the_owner(self, boss, company):
        admin, client = boss
        owner = company.users.get(role="owner")
        member = make_company_user(company, role="member")
        company_session(owner)
        company_session(member)
        response = post(client, f"/api/admin/companies/{company.pk}/suspend/", reason=REASON)
        assert response.status_code == 200
        company.refresh_from_db()
        assert company.status == Company.Status.SUSPENDED
        assert live_sessions(owner) == live_sessions(member) == 0
        assert len(owner_emails(company)) == 1
        event = last_event("admin.company_suspended")
        assert (event.actor_id, event.reason, event.company_id) == (admin.pk, REASON, company.pk)

    def test_the_company_sees_the_suspended_message_at_sign_in(self, boss, company):
        _, client = boss
        post(client, f"/api/admin/companies/{company.pk}/suspend/", reason=REASON)
        owner = company.users.get(role="owner")
        owner.set_password("Correct-Horse-9-Battery")
        owner.save()
        response = APIClient().post(
            "/api/auth/company/login/",
            {"email": owner.email, "password": "Correct-Horse-9-Battery"},
            format="json",
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "company_suspended"
        assert "suspended" in response.json()["error"]["message"]

    def test_suspending_twice_is_refused(self, boss, company):
        _, client = boss
        post(client, f"/api/admin/companies/{company.pk}/suspend/", reason=REASON)
        again = post(client, f"/api/admin/companies/{company.pk}/suspend/", reason=REASON)
        assert (again.status_code, again.json()["error"]["code"]) == (409, "already_suspended")
        assert AuditEvent.objects.filter(kind="admin.company_suspended").count() == 1

    def test_unsuspending_restores_the_company_and_emails_the_owner(self, boss, company):
        _, client = boss
        post(client, f"/api/admin/companies/{company.pk}/suspend/", reason=REASON)
        response = post(client, f"/api/admin/companies/{company.pk}/unsuspend/", reason=REASON)
        assert response.status_code == 200
        company.refresh_from_db()
        assert company.status == Company.Status.ACTIVE
        assert len(owner_emails(company)) == 2
        assert last_event("admin.company_unsuspended").reason == REASON

    def test_old_sessions_do_not_come_back_after_unsuspending(self, boss, company):
        _, client = boss
        owner = company.users.get(role="owner")
        issued = company_session(owner)
        post(client, f"/api/admin/companies/{company.pk}/suspend/", reason=REASON)
        post(client, f"/api/admin/companies/{company.pk}/unsuspend/", reason=REASON)
        old = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert old.get("/api/company/team/members/").status_code == 401

    def test_unsuspending_an_active_company_is_refused(self, boss, company):
        _, client = boss
        response = post(client, f"/api/admin/companies/{company.pk}/unsuspend/", reason=REASON)
        assert (response.status_code, response.json()["error"]["code"]) == (409, "not_suspended")


class TestLimits:
    URL = "/api/admin/companies/{}/limits/{}/"

    def put(self, client, company, name, **body):
        return client.put(self.URL.format(company.pk, name), body, format="json")

    def test_it_raises_a_limit_at_once_and_emails_the_owner(self, boss, company, plan):
        admin, client = boss
        subs.activate(
            company.pk, plan, period_start=timezone.now(), period_end=timezone.now() + 30 * DAY
        )
        for _ in range(5):
            cv = uuid.uuid4()
            usage.accept_cv(company.pk, cv)
            usage.mark_scored(company.pk, cv)
        assert not limits.check_cvs_this_month(company.pk).allowed
        assert self.put(client, company, "cvs_per_month", value=9, reason=REASON).status_code == 200
        assert limits.check_cvs_this_month(company.pk).allowed
        emails = owner_emails(company)
        assert len(emails) == 2  # subscription activated, then the limit change
        event = last_event("admin.limit_changed")
        assert event.details["changes"]["value"] == {"old": 5, "new": 9}
        assert (event.actor_id, event.reason) == (admin.pk, REASON)

    def test_it_can_also_lower_a_limit_without_deleting_anything(self, boss, company, plan):
        _, client = boss
        subs.activate(
            company.pk, plan, period_start=timezone.now(), period_end=timezone.now() + 30 * DAY
        )
        for _ in range(4):
            cv = uuid.uuid4()
            usage.accept_cv(company.pk, cv)
            usage.mark_scored(company.pk, cv)
        assert self.put(client, company, "cvs_per_month", value=2, reason=REASON).status_code == 200
        check = limits.check_cvs_this_month(company.pk)
        assert (check.allowed, check.used, check.limit) == (False, 4, 2)
        assert usage.current_usage(company.pk)["cvs_scored"] == 4  # nothing was removed

    def test_clearing_returns_to_the_plan_value(self, boss, company, plan):
        _, client = boss
        subs.activate(
            company.pk, plan, period_start=timezone.now(), period_end=timezone.now() + 30 * DAY
        )
        self.put(client, company, "cvs_per_month", value=50, reason=REASON)
        response = client.delete(
            self.URL.format(company.pk, "cvs_per_month"), {"reason": REASON}, format="json"
        )
        assert response.status_code == 204
        assert limits.limit_for(company.pk, "cvs_per_month") == 5
        event = last_event("admin.limit_changed")
        assert event.details["changes"]["value"] == {"old": 50, "new": 5}

    def test_clearing_nothing_is_refused(self, boss, company):
        _, client = boss
        response = client.delete(
            self.URL.format(company.pk, "cvs_per_month"), {"reason": REASON}, format="json"
        )
        assert (response.status_code, response.json()["error"]["code"]) == (409, "no_override")

    def test_setting_the_same_value_changes_nothing(self, boss, company):
        _, client = boss
        self.put(client, company, "max_projects", value=4, reason=REASON)
        again = self.put(client, company, "max_projects", value=4, reason=REASON)
        assert again.status_code == 400
        assert AuditEvent.objects.filter(kind="admin.limit_changed").count() == 1

    @pytest.mark.parametrize("value", [0, -1, 2.5, "7", True, None, 2_000_000_001])
    def test_a_value_must_be_a_positive_whole_number(self, boss, company, value):
        _, client = boss
        response = self.put(client, company, "max_projects", value=value, reason=REASON)
        assert response.status_code == 400
        assert not LimitOverride.objects.exists()

    def test_an_unknown_limit_is_not_found(self, boss, company):
        _, client = boss
        assert self.put(client, company, "nonsense", value=3, reason=REASON).status_code == 404

    def test_it_changes_only_that_company(self, boss, company):
        _, client = boss
        other = make_company()
        self.put(client, company, "max_projects", value=9, reason=REASON)
        assert limits.limit_for(other.pk, "max_projects") == 0


class TestFreeSubscriptions:
    BASE = "/api/admin/companies/{}/subscription/{}/"

    def grant(self, client, company, plan, days=30, **extra):
        return post(
            client,
            self.BASE.format(company.pk, "grant-free"),
            plan_id=plan.pk,
            period_end=(timezone.now() + days * DAY).isoformat(),
            reason=REASON,
            **extra,
        )

    def test_a_free_period_gives_access_and_emails_the_owner(self, boss, company, plan):
        admin, client = boss
        response = self.grant(client, company, plan)
        assert response.status_code == 200 and response.json()["state"] == "granted_free"
        assert subs.can_upload(company.pk)
        assert len(owner_emails(company)) == 1
        assert last_event("admin.free_subscription_granted").reason == REASON

    def test_the_end_must_be_in_the_future_and_the_plan_must_exist(self, boss, company, plan):
        _, client = boss
        assert self.grant(client, company, plan, days=-1).status_code == 400
        missing = post(
            client,
            self.BASE.format(company.pk, "grant-free"),
            plan_id=99999,
            period_end=(timezone.now() + DAY).isoformat(),
            reason=REASON,
        )
        assert missing.status_code == 404

    def test_it_is_refused_while_a_subscription_still_gives_access(self, boss, company, plan):
        _, client = boss
        subs.activate(
            company.pk, plan, period_start=timezone.now(), period_end=timezone.now() + 30 * DAY
        )
        assert self.grant(client, company, plan).status_code == 409

    def test_a_free_grant_can_be_ended_early(self, boss, company, plan):
        _, client = boss
        self.grant(client, company, plan)
        response = post(client, self.BASE.format(company.pk, "end-free"), reason=REASON)
        assert response.status_code == 200 and response.json()["state"] == "expired"
        assert not subs.can_upload(company.pk)
        assert last_event("admin.free_subscription_ended").reason == REASON
        assert len(owner_emails(company)) == 2

    def test_ending_without_a_free_grant_is_refused(self, boss, company):
        _, client = boss
        response = post(client, self.BASE.format(company.pk, "end-free"), reason=REASON)
        assert response.status_code == 409


class TestTerminating:
    URL = "/api/admin/companies/{}/subscription/terminate/"

    def paid(self, company, plan):
        subs.activate(
            company.pk, plan, period_start=timezone.now(), period_end=timezone.now() + 30 * DAY
        )

    def test_it_ends_access_now_and_the_company_sees_the_renewal_prompt(self, boss, company, plan):
        admin, client = boss
        self.paid(company, plan)
        response = post(client, self.URL.format(company.pk), reason=REASON)
        assert response.status_code == 200 and response.json()["state"] == "expired"
        assert not subs.can_upload(company.pk)
        check = limits.check_projects(company.pk, 0)
        assert (check.code, check.prompt) == ("subscription_expired", "renewal")
        assert "ended" in check.message
        event = last_event("admin.subscription_terminated")
        assert (event.actor_id, event.reason) == (admin.pk, REASON)
        assert len(owner_emails(company)) == 2

    def test_data_and_people_are_kept(self, boss, company, plan):
        _, client = boss
        self.paid(company, plan)
        cv = uuid.uuid4()
        usage.accept_cv(company.pk, cv)
        usage.mark_scored(company.pk, cv)
        post(client, self.URL.format(company.pk), reason=REASON)
        assert usage.current_usage(company.pk)["cvs_scored"] == 1
        assert subs.can_view(company.pk)
        assert Company.objects.filter(pk=company.pk).exists()
        assert CompanyUser.objects.filter(company=company).count() == 1

    def test_the_company_can_still_sign_in(self, boss, company, plan):
        _, client = boss
        self.paid(company, plan)
        post(client, self.URL.format(company.pk), reason=REASON)
        company.refresh_from_db()
        assert company.status == Company.Status.ACTIVE

    def test_terminating_an_already_ended_subscription_is_refused(self, boss, company):
        _, client = boss
        assert post(client, self.URL.format(company.pk), reason=REASON).status_code == 409


class TestResettingAnAdminsTwoStep:
    def target(self):
        return make_admin_user(
            role="support",
            two_step_enabled=True,
            two_step_secret="FAKESECRET",
            two_step_last_step=5,
        )

    def url(self, admin):
        return f"/api/admin/admin-users/{admin.pk}/two-step/reset/"

    def test_it_clears_the_authenticator_and_ends_all_their_sessions(self, boss):
        admin, client = boss
        target = self.target()
        signin.start_session(user_id=target.pk, role="support", company_id=None, kind="admin")
        signin.start_session(user_id=target.pk, role="support", company_id=None, kind="admin")
        assert live_sessions(target, "admin") == 2
        response = post(client, self.url(target), reason=REASON)
        assert response.status_code == 200
        target.refresh_from_db()
        assert (target.two_step_enabled, target.two_step_secret, target.two_step_last_step) == (
            False,
            "",
            None,
        )
        assert live_sessions(target, "admin") == 0
        event = last_event("admin.two_step_reset")
        assert (event.actor_id, event.target_id, event.reason) == (admin.pk, str(target.pk), REASON)

    def test_they_must_enrol_again_at_the_next_login(self, boss):
        _, client = boss
        target = self.target()
        target.set_password("Correct-Horse-9-Battery")
        target.save()
        post(client, self.url(target), reason=REASON)
        response = APIClient().post(
            "/api/auth/admin/login/",
            {"email": target.email, "password": "Correct-Horse-9-Battery"},
            format="json",
        )
        assert response.json()["status"] == "two_step_setup_required"

    def test_an_admin_cannot_reset_their_own(self, boss):
        admin, client = boss
        admin.two_step_enabled = True
        admin.save()
        response = post(client, self.url(admin), reason=REASON)
        assert (response.status_code, response.json()["error"]["code"]) == (403, "own_account")
        admin.refresh_from_db()
        assert admin.two_step_enabled
        assert not AuditEvent.objects.filter(kind="admin.two_step_reset").exists()

    def test_a_reason_is_required_and_nothing_changes_without_it(self, boss):
        _, client = boss
        target = self.target()
        assert post(client, self.url(target)).status_code == 400
        assert post(client, self.url(target), reason=" ").status_code == 400
        target.refresh_from_db()
        assert target.two_step_enabled

    def test_support_cannot_do_it(self):
        support = make_admin_user(role="support")
        target = self.target()
        response = post(client_for(support), self.url(target), reason=REASON)
        assert response.status_code == 403
        target.refresh_from_db()
        assert target.two_step_enabled

    def test_without_two_step_on_it_is_refused(self, boss):
        _, client = boss
        target = make_admin_user(role="support")
        assert post(client, self.url(target), reason=REASON).status_code == 409


class TestTurningOffACompanyUsersTwoStep:
    def person(self, company):
        user = make_company_user(
            company,
            role="member",
            email_verified=True,
            two_step_enabled=True,
            two_step_secret="FAKESECRET",
        )
        RecoveryCode.objects.create(user=user, code_hash="a" * 64)
        return user

    def url(self, user):
        return f"/api/admin/company-users/{user.pk}/two-step/off/"

    def test_it_turns_it_off_signs_them_out_and_emails_them(self, boss, company):
        admin, client = boss
        user = self.person(company)
        company_session(user)
        response = post(
            client, self.url(user), reason="Checked photo ID by video call.", identity_checked=True
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert (user.two_step_enabled, user.two_step_secret) == (False, "")
        assert not RecoveryCode.objects.filter(user=user).exists()
        assert live_sessions(user) == 0
        mails = [e for e in OutgoingEmail.objects.all() if e.to_address == user.email]
        assert len(mails) == 1 and mails[0].template == "account_notice"
        event = last_event("admin.company_two_step_off")
        assert (event.actor_id, event.reason) == (admin.pk, "Checked photo ID by video call.")
        assert event.details["identity_checked"] is True

    @pytest.mark.parametrize("checked", [False, None, "yes", 1])
    def test_the_identity_check_must_be_confirmed(self, boss, company, checked):
        _, client = boss
        user = self.person(company)
        response = post(client, self.url(user), reason=REASON, identity_checked=checked)
        assert response.status_code == 400
        user.refresh_from_db()
        assert user.two_step_enabled
        assert not AuditEvent.objects.filter(kind="admin.company_two_step_off").exists()

    def test_a_reason_is_required(self, boss, company):
        _, client = boss
        user = self.person(company)
        assert post(client, self.url(user), identity_checked=True).status_code == 400
        user.refresh_from_db()
        assert user.two_step_enabled

    def test_support_cannot_do_it(self, company):
        user = self.person(company)
        support = make_admin_user(role="support")
        response = post(client_for(support), self.url(user), reason=REASON, identity_checked=True)
        assert response.status_code == 403
        user.refresh_from_db()
        assert user.two_step_enabled

    def test_without_two_step_on_it_is_refused(self, boss, company):
        _, client = boss
        user = make_company_user(company, role="member")
        response = post(client, self.url(user), reason=REASON, identity_checked=True)
        assert response.status_code == 409

    def test_an_unknown_person_is_not_found(self, boss):
        _, client = boss
        response = post(
            client,
            "/api/admin/company-users/999999/two-step/off/",
            reason=REASON,
            identity_checked=True,
        )
        assert response.status_code == 404


def test_every_admin_action_is_in_the_audit_log_with_the_admin_as_actor(boss, company):
    admin, client = boss
    post(client, f"/api/admin/companies/{company.pk}/suspend/", reason=REASON)
    post(client, f"/api/admin/companies/{company.pk}/unsuspend/", reason=REASON)
    events = AuditEvent.objects.filter(kind__startswith="admin.company_")
    assert events.count() == 2
    assert {(e.actor_kind, e.actor_id) for e in events} == {("admin", admin.pk)}
    assert AdminUser.objects.filter(pk=admin.pk).exists()
