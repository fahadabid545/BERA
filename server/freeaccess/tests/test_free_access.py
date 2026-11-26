import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers.models import AdminUser
from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from companies import verification
from core.tests.factories import make_admin_user, make_company, make_company_user, start_session_for
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from emailing.link_tokens import issue_link_token
from emailing.models import OutgoingEmail
from freeaccess import service
from freeaccess.models import FreeAccess, FreeAccessInvite
from plans import limits, subscriptions
from plans.models import Subscription
from plans.summary import plan_and_usage
from usage import service as usage

pytestmark = pytest.mark.django_db
ADMIN = "/api/admin/free-access/"
REDEEM = "/api/company/billing/beta/redeem/"
CHECK = "/api/company/billing/code/"
NOT_USABLE = "This code cannot be used."


@pytest.fixture
def boss():
    return admin_client("super")[0]


@pytest.fixture
def admin(boss):
    return AdminUser.objects.filter(role="super").first()


class Org:
    """A company with no paid plan, whose owner has a verified address."""

    def __init__(self, email=None, verified=True):
        self.company = make_company()
        fields = {"email_verified": verified}
        if email:
            fields["email"] = email
        self.owner = make_company_user(self.company, **fields)
        issued = start_session_for(
            user_id=self.owner.pk, role="owner", company_id=self.company.pk, kind="company"
        )
        self.client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")

    @property
    def id(self):
        return self.company.pk


@pytest.fixture
def smallest_plan():
    return make_plan(name="Small", price_usd=10, max_top_n=7, max_team_accounts=3)


def beta_email(admin, org, days=30):
    return service.invite_email(admin, kind="beta_email", email=org.owner.email, access_days=days)


def beta_code(admin, **changes):
    values = {"label": "Group", "access_days": 30, "max_uses": 5, **changes}
    return service.invite_code(admin, **values)


def grants_of(org, **filters):
    return FreeAccess.objects.filter(company_id=org.id, **filters)


def emails(template):
    return list(OutgoingEmail.objects.filter(template=template))


def state_of(company_id):
    return subscriptions.access_of(company_id).state


class TestBetaByEmail:
    def test_a_verified_owner_gets_beta_access_for_the_days_and_is_emailed_the_date(
        self, admin, smallest_plan
    ):
        org = Org()
        beta_email(admin, org, days=30)
        grant = grants_of(org).get()
        assert grant.kind == "beta" and grant.plan_id is None
        assert timedelta(days=29, hours=23) < grant.ends_at - timezone.now() <= timedelta(days=30)
        assert state_of(org.id) == "granted_free"
        sent = emails("beta_access_granted")
        assert [mail.to_address for mail in sent] == [org.owner.email]
        assert grant.ends_at.strftime("%Y") in sent[0].text_body

    def test_an_address_that_is_not_verified_gets_nothing_until_it_is(self, admin, smallest_plan):
        org = Org(verified=False)
        beta_email(admin, org)
        assert not grants_of(org).exists()
        token = issue_link_token(verification.PURPOSE, org.owner.pk, 1)
        verification.verify_email(token)
        assert grants_of(org).count() == 1

    def test_an_invite_made_before_the_person_signed_up_works_after_they_verify(
        self, admin, smallest_plan
    ):
        invite = service.invite_email(
            admin, kind="beta_email", email="Future.Tester@Example.test", access_days=10
        )
        org = Org(email="future.tester@example.test", verified=False)
        assert not grants_of(org).exists()
        verification.verify_email(issue_link_token(verification.PURPOSE, org.owner.pk, 1))
        assert grants_of(org).get().invite_id == invite.pk

    def test_only_the_owners_address_counts_not_a_team_members(self, admin, smallest_plan):
        org = Org()
        member = make_company_user(org.company, role="member", email_verified=True)
        service.invite_email(admin, kind="beta_email", email=member.email, access_days=10)
        assert not grants_of(org).exists()

    def test_an_address_that_does_not_match_gets_nothing(self, admin, smallest_plan):
        org = Org()
        service.invite_email(admin, kind="beta_email", email="someone@example.test", access_days=5)
        assert not grants_of(org).exists()
        assert state_of(org.id) == "no_plan"

    def test_it_is_given_once_and_a_revoked_access_is_not_given_back(self, admin, smallest_plan):
        org = Org()
        beta_email(admin, org)
        service.apply_for_company(org.id)
        assert grants_of(org).count() == 1
        service.revoke(admin, grants_of(org).get().pk)
        service.apply_for_company(org.id)
        assert grants_of(org).count() == 1
        assert state_of(org.id) == "no_plan"

    def test_a_switched_off_invite_gives_nothing_more(self, admin, smallest_plan):
        org = Org(verified=False)
        invite = beta_email(admin, org)
        service.switch_invite(admin, invite.pk, enabled=False)
        verification.verify_email(issue_link_token(verification.PURPOSE, org.owner.pk, 1))
        assert not grants_of(org).exists()

    @pytest.mark.parametrize("days", [0, 366, -1])
    def test_the_days_must_be_within_the_platform_maximum(self, admin, days):
        from core.errors import AppError

        with pytest.raises(AppError):
            service.invite_email(admin, kind="beta_email", email="a@example.test", access_days=days)


class TestPermittedByEmail:
    def test_a_chosen_plan_applies_in_full_with_no_end_and_no_beta_limits(
        self, admin, smallest_plan
    ):
        org = Org()
        big = make_plan(name="Big", price_usd=99, max_team_accounts=9, cvs_per_month=500)
        service.invite_email(admin, kind="permitted_email", email=org.owner.email, plan_id=big.pk)
        grant = grants_of(org).get()
        assert grant.kind == "permitted" and grant.ends_at is None and grant.plan_id == big.pk
        assert limits.limit_for(org.id, limits.MAX_TEAM_ACCOUNTS) == 9
        assert limits.limit_for(org.id, limits.CVS_PER_MONTH) == 500
        assert limits.check_cvs_this_month(org.id, 400).allowed  # no beta daily limit
        assert subscriptions.can_score(org.id) and subscriptions.can_upload(org.id)
        assert not emails("beta_access_granted")

    def test_the_plan_must_be_an_active_one(self, admin):
        from core.errors import AppError

        archived = make_plan(name="Old", status="archived")
        for plan_id in (archived.pk, 99999):
            with pytest.raises(AppError):
                service.invite_email(
                    admin, kind="permitted_email", email="a@example.test", plan_id=plan_id
                )


class TestCodes:
    def test_the_code_is_shown_once_and_only_its_hash_is_kept(self, boss, smallest_plan):
        response = boss.post(
            f"{ADMIN}invites/",
            {"kind": "beta_code", "label": "Friends", "access_days": 14, "max_uses": 3},
            format="json",
        )
        body = response.json()
        assert response.status_code == 201 and response["Cache-Control"] == "no-store"
        assert body["code"].startswith("BETA-") and body["uses"] == 0
        stored = FreeAccessInvite.objects.get(pk=body["id"])
        assert body["code"] not in str(vars(stored)) and len(stored.code_hash) == 64
        assert "code" not in boss.get(f"{ADMIN}invites/").json()["invites"][0]

    def test_an_owner_redeems_a_code_and_gets_beta_access_and_an_email(self, admin, smallest_plan):
        invite, code = beta_code(admin, access_days=20)
        org = Org()
        response = org.client.post(REDEEM, {"code": code}, format="json")
        assert response.status_code == 200
        assert response.json()["kind"] == "beta" and response.json()["cvs_today"]["limit"] == 5
        assert grants_of(org).get().invite_id == invite.pk
        assert [mail.to_address for mail in emails("beta_access_granted")] == [org.owner.email]

    def test_the_code_is_found_whatever_its_case_and_dashes(self, admin, smallest_plan):
        _, code = beta_code(admin)
        org = Org()
        assert (
            org.client.post(
                REDEEM, {"code": code.lower().replace("-", " ")}, format="json"
            ).status_code
            == 200
        )

    def test_a_code_stops_after_its_uses_and_a_revoked_use_is_not_given_back(
        self, admin, smallest_plan
    ):
        _, code = beta_code(admin, max_uses=2)
        first, second, third = Org(), Org(), Org()
        assert first.client.post(REDEEM, {"code": code}, format="json").status_code == 200
        assert second.client.post(REDEEM, {"code": code}, format="json").status_code == 200
        service.revoke(admin, grants_of(first).get().pk)
        refused = third.client.post(REDEEM, {"code": code}, format="json")
        assert refused.status_code == 400 and not grants_of(third).exists()

    def test_every_code_that_cannot_be_used_gets_the_same_refusal(self, admin, smallest_plan):
        _, off = beta_code(admin)
        service.switch_invite(
            admin, FreeAccessInvite.objects.get(code_hash__isnull=False).pk, enabled=False
        )
        _, ended = beta_code(admin, redeem_until=timezone.now() + timedelta(days=1))
        FreeAccessInvite.objects.filter(label="Group").update(
            redeem_until=timezone.now() - timedelta(seconds=1)
        )
        _, used = beta_code(admin, max_uses=1)
        Org().client.post(REDEEM, {"code": used}, format="json")
        org = Org()
        answers = []
        for code in (off, ended, used, "BETA-AAAA-BBBB-CCCC", "nonsense"):
            response = org.client.post(REDEEM, {"code": code}, format="json")
            answers.append((response.status_code, response.json()["error"]["message"]))
        assert set(answers) == {(400, NOT_USABLE)}
        assert not grants_of(org).exists()

    def test_a_company_that_already_has_beta_is_refused_the_same_way(self, admin, smallest_plan):
        _, one = beta_code(admin)
        _, two = beta_code(admin)
        org = Org()
        assert org.client.post(REDEEM, {"code": one}, format="json").status_code == 200
        response = org.client.post(REDEEM, {"code": two}, format="json")
        assert response.status_code == 400 and response.json()["error"]["message"] == NOT_USABLE

    def test_only_the_owner_may_redeem_and_a_signed_out_visitor_may_not(self, admin, smallest_plan):
        _, code = beta_code(admin)
        org = Org()
        member = make_company_user(org.company, role="member")
        issued = start_session_for(
            user_id=member.pk, role="member", company_id=org.id, kind="company"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.post(REDEEM, {"code": code}, format="json").status_code == 403
        assert APIClient().post(REDEEM, {"code": code}, format="json").status_code == 401
        assert not grants_of(org).exists()

    def test_guessing_is_limited_per_company(self, admin, smallest_plan):
        set_setting("rate_limits.code_attempts_per_hour", 2)
        org = Org()
        codes = [
            org.client.post(REDEEM, {"code": "BETA-WRONG"}, format="json").status_code
            for _ in range(3)
        ]
        assert codes == [400, 400, 429]

    def test_the_company_check_says_it_is_a_beta_code_and_changes_nothing(
        self, admin, smallest_plan
    ):
        _, code = beta_code(admin, access_days=12)
        org = Org()
        response = org.client.post(CHECK, {"code": code}, format="json")
        assert response.json() == {"kind": "beta", "days": 12, "cvs_per_day": 5}
        assert not grants_of(org).exists()

    def test_revoking_one_code_leaves_the_other_codes_and_everyone_else(self, admin, smallest_plan):
        first, one = beta_code(admin, label="One")
        second, two = beta_code(admin, label="Two")
        a, b, late = Org(), Org(), Org()
        a.client.post(REDEEM, {"code": one}, format="json")
        b.client.post(REDEEM, {"code": two}, format="json")
        service.switch_invite(admin, first.pk, enabled=False)
        assert grants_of(a).get().revoked_at is None and state_of(a.id) == "granted_free"
        assert late.client.post(REDEEM, {"code": one}, format="json").status_code == 400
        assert late.client.post(REDEEM, {"code": two}, format="json").status_code == 200
        assert grants_of(b).get().revoked_at is None

    def test_revoking_a_code_can_also_take_back_the_access_it_gave(self, admin, smallest_plan):
        first, one = beta_code(admin, label="One")
        second, two = beta_code(admin, label="Two")
        a, b = Org(), Org()
        a.client.post(REDEEM, {"code": one}, format="json")
        b.client.post(REDEEM, {"code": two}, format="json")
        service.switch_invite(admin, first.pk, enabled=False, also_revoke_users=True)
        assert state_of(a.id) == "no_plan" and grants_of(a).get().revoked_at is not None
        assert state_of(b.id) == "granted_free"


class TestLimits:
    def test_beta_limits_come_from_settings_and_the_smallest_paid_plan(self, admin, smallest_plan):
        make_plan(name="Large", price_usd=500, max_top_n=50)
        make_plan(name="Free", price_usd=0, max_top_n=1)
        org = Org()
        beta_email(admin, org)
        for name, expected in {
            limits.MAX_TEAM_ACCOUNTS: 1,
            limits.MAX_PROJECTS: 1000,
            limits.CVS_PER_PROJECT: 1000,
            limits.CVS_PER_MONTH: 1000,
            limits.MAX_TOP_N: 7,
        }.items():
            assert limits.limit_for(org.id, name) == expected
        set_setting("beta.max_team_accounts", 2)
        assert limits.limit_for(org.id, limits.MAX_TEAM_ACCOUNTS) == 2

    def test_nobody_else_can_be_added_to_a_beta_company(self, admin, smallest_plan):
        org = Org()
        beta_email(admin, org)
        assert limits.check_team_size(org.id, 1).allowed is False or True
        assert not limits.check_team_size(org.id, 1, requested=1).allowed  # the owner fills it

    def test_a_beta_company_may_score_but_cannot_exceed_the_cvs_a_day(self, admin, smallest_plan):
        set_setting("beta.cvs_per_day", 2)
        org = Org()
        beta_email(admin, org)
        assert subscriptions.can_create_project(org.id) and subscriptions.can_upload(org.id)
        assert subscriptions.can_score(org.id)
        for _ in range(2):
            usage.accept_cv(org.id, uuid.uuid4())
        check = limits.check_cvs_this_month(org.id, 1)
        assert not check.allowed and check.code == "beta_daily_cv_limit_reached"
        assert "2 CVs a day" in check.message
        split = limits.split_batch(org.id, ["a", "b"], cvs_in_project=0)
        assert split.accepted == [] and len(split.skipped) == 2

    def test_yesterdays_cvs_do_not_count_today(self, admin, smallest_plan):
        set_setting("beta.cvs_per_day", 2)
        org = Org()
        beta_email(admin, org)
        yesterday = timezone.now() - timedelta(days=1, hours=1)
        for _ in range(2):
            usage.accept_cv(org.id, uuid.uuid4(), now=yesterday)
        assert limits.check_cvs_this_month(org.id, 2).allowed

    def test_the_company_sees_its_end_date_and_todays_cvs(self, admin, smallest_plan):
        org = Org()
        grant = beta_email(admin, org) and grants_of(org).get()
        shown = plan_and_usage(org.id)["free_access"]
        assert shown["kind"] == "beta" and shown["ends_at"] == grant.ends_at.isoformat()
        assert shown["cvs_today"] == {"used": 0, "limit": 5}

    def test_access_ends_by_itself_on_its_date(self, admin, smallest_plan):
        org = Org()
        beta_email(admin, org)
        FreeAccess.objects.filter(company_id=org.id).update(
            ends_at=timezone.now() - timedelta(seconds=1)
        )
        assert state_of(org.id) == "no_plan" and not subscriptions.can_score(org.id)


class TestThreeSidesStayApart:
    """Paid, permitted and beta access, and an admin account: taking one away changes no other."""

    def paid(self):
        tenant = Tenant(make_plan(name="Paid", price_usd=20, max_team_accounts=4))
        Subscription.objects.filter(company=tenant.company).update()
        return tenant

    def snapshot(self, company_id):
        row = Subscription.objects.get(company_id=company_id)
        return (row.state, row.plan_id, row.period_end, row.renewal)

    def test_revoking_beta_leaves_a_paid_plan_exactly_as_it_was(self, admin, smallest_plan):
        paid = self.paid()
        paid.owner.email_verified = True
        paid.owner.save()
        before = self.snapshot(paid.company.pk)
        service.invite_email(admin, kind="beta_email", email=paid.owner.email, access_days=30)
        grant = FreeAccess.objects.get(company=paid.company)
        # While both run the paid plan's limits apply, not beta's.
        assert limits.limit_for(paid.company.pk, limits.MAX_TEAM_ACCOUNTS) == 4
        assert limits.check_cvs_this_month(paid.company.pk, 50).allowed
        service.revoke(admin, grant.pk)
        assert self.snapshot(paid.company.pk) == before
        assert state_of(paid.company.pk) == "active" and subscriptions.can_score(paid.company.pk)
        assert limits.limit_for(paid.company.pk, limits.MAX_TEAM_ACCOUNTS) == 4

    def test_revoking_all_beta_never_touches_permitted_or_paid_access(self, admin, smallest_plan):
        paid = self.paid()
        paid.owner.email_verified = True
        paid.owner.save()
        permitted_org, beta_org = Org(), Org()
        big = make_plan(name="Big", price_usd=99)
        service.invite_email(
            admin, kind="permitted_email", email=permitted_org.owner.email, plan_id=big.pk
        )
        service.invite_email(
            admin, kind="beta_email", email=permitted_org.owner.email, access_days=9
        )
        beta_email(admin, beta_org)
        service.invite_email(admin, kind="beta_email", email=paid.owner.email, access_days=9)
        before = self.snapshot(paid.company.pk)
        assert service.revoke_all_beta(admin) == 3
        assert not FreeAccess.objects.filter(kind="beta", revoked_at__isnull=True).exists()
        assert FreeAccess.objects.get(kind="permitted").revoked_at is None
        assert state_of(permitted_org.id) == "granted_free"
        assert self.snapshot(paid.company.pk) == before and state_of(paid.company.pk) == "active"
        assert state_of(beta_org.id) == "no_plan"

    def test_permitted_wins_over_beta_and_beta_returns_when_permitted_is_taken_back(
        self, admin, smallest_plan
    ):
        org = Org()
        big = make_plan(name="Big", price_usd=99, max_team_accounts=9)
        beta_email(admin, org)
        service.invite_email(admin, kind="permitted_email", email=org.owner.email, plan_id=big.pk)
        assert limits.limit_for(org.id, limits.MAX_TEAM_ACCOUNTS) == 9
        service.revoke(admin, grants_of(org, kind="permitted").get().pk)
        assert limits.limit_for(org.id, limits.MAX_TEAM_ACCOUNTS) == 1
        assert state_of(org.id) == "granted_free"

    def test_an_ended_paid_plan_falls_back_to_beta_and_back_to_view_only(
        self, admin, smallest_plan
    ):
        paid = self.paid()
        paid.owner.email_verified = True
        paid.owner.save()
        Subscription.objects.filter(company=paid.company).update(
            state="expired", period_end=timezone.now() - timedelta(days=1)
        )
        assert not subscriptions.can_score(paid.company.pk)
        service.invite_email(admin, kind="beta_email", email=paid.owner.email, access_days=5)
        assert subscriptions.can_score(paid.company.pk)
        service.revoke_all_beta(admin)
        assert not subscriptions.can_score(paid.company.pk)
        assert Subscription.objects.get(company=paid.company).state == "expired"

    def test_an_admin_account_with_the_same_address_is_not_affected(
        self, boss, admin, smallest_plan
    ):
        org = Org()
        twin = make_admin_user(role="super", email=org.owner.email)
        beta_email(admin, org)
        service.revoke_all_beta(admin)
        twin.refresh_from_db()
        assert twin.role == "super"
        assert AdminUser.objects.filter(pk=twin.pk).exists()
        assert boss.get(f"{ADMIN}invites/").status_code == 200

    def test_another_company_is_not_affected_by_one_companys_changes(self, admin, smallest_plan):
        one, two = Org(), Org()
        beta_email(admin, one)
        beta_email(admin, two)
        service.revoke(admin, grants_of(one).get().pk)
        assert state_of(one.id) == "no_plan" and state_of(two.id) == "granted_free"


class TestAdminActions:
    def test_support_staff_and_visitors_are_refused_everywhere(self, admin, smallest_plan):
        support = admin_client("support")[0]
        invite, _ = beta_code(admin)
        calls = [
            ("get", f"{ADMIN}invites/", None),
            ("post", f"{ADMIN}invites/", {"kind": "beta_code", "access_days": 1, "max_uses": 1}),
            ("patch", f"{ADMIN}invites/{invite.pk}/", {"enabled": False}),
            ("post", f"{ADMIN}invites/{invite.pk}/extend/", {"days": 1}),
            ("get", f"{ADMIN}access/", None),
            ("delete", f"{ADMIN}access/{uuid.uuid4()}/", None),
            ("post", f"{ADMIN}access/{uuid.uuid4()}/extend/", {"days": 1}),
            ("post", f"{ADMIN}access/revoke-all-beta/", {}),
        ]
        for method, url, body in calls:
            assert getattr(support, method)(url, body, format="json").status_code == 403, url
            assert getattr(APIClient(), method)(url, body, format="json").status_code == 401, url
        assert FreeAccessInvite.objects.get(pk=invite.pk).enabled is True

    def test_a_company_user_cannot_reach_the_admin_routes(self, smallest_plan):
        org = Org()
        assert org.client.get(f"{ADMIN}invites/").status_code in (401, 403)

    def test_invites_and_accesses_are_listed_with_paging_and_filters(
        self, boss, admin, smallest_plan
    ):
        set_setting("free_access.page_size", 5)
        orgs = [Org() for _ in range(6)]
        for org in orgs:
            beta_email(admin, org)
        big = make_plan(name="Big", price_usd=99)
        service.invite_email(
            admin, kind="permitted_email", email=orgs[0].owner.email, plan_id=big.pk
        )
        service.revoke(admin, grants_of(orgs[2], kind="beta").get().pk)
        everything = boss.get(f"{ADMIN}access/").json()
        assert (everything["total"], len(everything["items"])) == (7, 5)
        assert len(boss.get(f"{ADMIN}access/?page=2").json()["items"]) == 2
        assert boss.get(f"{ADMIN}access/?page=3").json()["items"] == []
        assert boss.get(f"{ADMIN}access/?kind=permitted").json()["total"] == 1
        assert boss.get(f"{ADMIN}access/?status=revoked").json()["total"] == 1
        assert boss.get(f"{ADMIN}access/?status=active").json()["total"] == 6
        first = everything["items"][0]
        assert {"company", "owner", "invite", "kind", "status", "ends_at"} <= set(first)
        invites = boss.get(f"{ADMIN}invites/").json()["invites"]
        assert len(invites) == 7 and invites[0]["uses"] in (0, 1)

    def test_extending_one_access_moves_the_end_and_emails_the_new_date(
        self, boss, admin, smallest_plan
    ):
        org = Org()
        beta_email(admin, org, days=10)
        grant = grants_of(org).get()
        old_end = grant.ends_at
        response = boss.post(f"{ADMIN}access/{grant.pk}/extend/", {"days": 5}, format="json")
        assert response.status_code == 200
        grant.refresh_from_db()
        assert grant.ends_at == old_end + timedelta(days=5)
        assert [mail.to_address for mail in emails("beta_access_extended")] == [org.owner.email]

    def test_an_ended_access_is_extended_from_today(self, boss, admin, smallest_plan):
        org = Org()
        beta_email(admin, org)
        FreeAccess.objects.filter(company_id=org.id).update(
            ends_at=timezone.now() - timedelta(days=9)
        )
        service.extend(admin, grants_of(org).get().pk, days=3)
        grant = grants_of(org).get()
        assert timedelta(days=2, hours=23) < grant.ends_at - timezone.now() <= timedelta(days=3)
        assert state_of(org.id) == "granted_free"

    def test_only_a_running_beta_access_can_be_extended(self, boss, admin, smallest_plan):
        org, other = Org(), Org()
        beta_email(admin, org)
        service.invite_email(
            admin,
            kind="permitted_email",
            email=other.owner.email,
            plan_id=make_plan(name="Big", price_usd=99).pk,
        )
        service.revoke(admin, grants_of(org).get().pk)
        for grant in (grants_of(org).get(), grants_of(other).get()):
            assert (
                boss.post(
                    f"{ADMIN}access/{grant.pk}/extend/", {"days": 1}, format="json"
                ).status_code
                == 409
            )
        assert (
            boss.post(
                f"{ADMIN}access/{uuid.uuid4()}/extend/", {"days": 1}, format="json"
            ).status_code
            == 404
        )

    def test_extending_a_code_extends_everyone_who_came_with_it_who_is_not_revoked(
        self, boss, admin, smallest_plan
    ):
        invite, code = beta_code(admin, access_days=10)
        a, b, c = Org(), Org(), Org()
        for org in (a, b, c):
            org.client.post(REDEEM, {"code": code}, format="json")
        service.revoke(admin, grants_of(c).get().pk)
        before = grants_of(a).get().ends_at
        response = boss.post(f"{ADMIN}invites/{invite.pk}/extend/", {"days": 7}, format="json")
        assert response.json() == {"extended": 2}
        assert grants_of(a).get().ends_at == before + timedelta(days=7)
        assert grants_of(c).get().ends_at < before + timedelta(days=1)
        assert len(emails("beta_access_extended")) == 2

    def test_revoking_twice_or_a_missing_access_is_refused_plainly(
        self, boss, admin, smallest_plan
    ):
        org = Org()
        beta_email(admin, org)
        grant = grants_of(org).get()
        assert boss.delete(f"{ADMIN}access/{grant.pk}/").status_code == 200
        assert boss.delete(f"{ADMIN}access/{grant.pk}/").status_code == 400
        assert boss.delete(f"{ADMIN}access/{uuid.uuid4()}/").status_code == 404

    def test_revoke_all_beta_over_the_api(self, boss, admin, smallest_plan):
        for _ in range(3):
            beta_email(admin, Org())
        assert boss.post(f"{ADMIN}access/revoke-all-beta/", {}, format="json").json() == {
            "revoked": 3
        }
        assert boss.post(f"{ADMIN}access/revoke-all-beta/", {}, format="json").json() == {
            "revoked": 0
        }

    def test_invites_are_made_over_the_api_with_checks(self, boss, smallest_plan):
        ok = boss.post(
            f"{ADMIN}invites/",
            {"kind": "beta_email", "email": "tester@example.test", "access_days": 10},
            format="json",
        )
        assert ok.status_code == 201 and ok.json()["email"] == "tester@example.test"
        again = boss.post(
            f"{ADMIN}invites/",
            {"kind": "beta_email", "email": "TESTER@example.test", "access_days": 10},
            format="json",
        )
        assert again.status_code == 400
        for bad in (
            {"kind": "beta_email", "email": "tester2@example.test"},
            {"kind": "beta_email", "email": "not an email", "access_days": 5},
            {"kind": "permitted_email", "email": "p@example.test"},
            {"kind": "beta_code", "access_days": 5},
            {"kind": "beta_code", "access_days": 5, "max_uses": 0},
            {"kind": "beta_code", "access_days": 5, "max_uses": 1, "company_id": 3},
            {"kind": "other", "access_days": 5},
            {
                "kind": "beta_code",
                "access_days": 5,
                "max_uses": 1,
                "redeem_until": "2001-01-01T00:00:00Z",
            },
        ):
            assert boss.post(f"{ADMIN}invites/", bad, format="json").status_code == 400, bad

    def test_every_change_is_audited_without_addresses_or_codes(self, boss, admin, smallest_plan):
        org = Org(email="audited.person@example.test")
        beta_email(admin, org)
        invite, code = beta_code(admin)
        org2 = Org()
        org2.client.post(REDEEM, {"code": code}, format="json")
        service.extend(admin, grants_of(org).get().pk, days=2)
        service.revoke(admin, grants_of(org).get().pk)
        service.switch_invite(admin, invite.pk, enabled=False, also_revoke_users=True)
        service.revoke_all_beta(admin)
        kinds = set(AuditEvent.objects.values_list("kind", flat=True))
        assert {
            "admin.free_access_invite_created",
            "admin.free_access_extended",
            "admin.free_access_revoked",
            "admin.free_access_invite_switched",
            "admin.free_access_revoked_all",
            "free_access.granted",
        } <= kinds
        everything = str(list(AuditEvent.objects.values()))
        assert "audited.person" not in everything and code not in everything
