import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers.tests.test_admin_roles import client_for
from audit.models import AuditEvent
from core.tests.factories import make_admin_user, make_company, make_company_user, start_session_for
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import make_plan
from emailing.models import OutgoingEmail
from notifications import billing_notices
from plans import limits, trials
from plans import subscriptions as subs
from plans.models import Subscription, TrialCode
from usage import service as usage

pytestmark = pytest.mark.django_db
CODES = "/api/admin/trials/codes/"
REDEEM = "/api/company/billing/trial/redeem/"
State = Subscription.State
REASON = "Fake reason for the test."


def signed_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}"), person


@pytest.fixture
def plan():
    return make_plan(cvs_per_month=100)


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner(company):
    return signed_in(company)[0]


@pytest.fixture
def boss():
    return client_for(make_admin_user(role="super"))


def new_code(boss, plan, **changes):
    body = {
        "name": "Fake campaign",
        "plan_id": plan.pk,
        "days": 14,
        "cv_limit": 50,
        "expires_at": (timezone.now() + timedelta(days=30)).isoformat(),
        **changes,
    }
    response = boss.post(CODES, body, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def kinds():
    return list(AuditEvent.objects.values_list("kind", flat=True))


def sub(company):
    return subs.get_subscription(company.pk)


class TestMakingCodes:
    def test_the_code_is_shown_once_and_only_its_hash_is_kept(self, boss, plan):
        body = new_code(boss, plan)
        assert body["code"].startswith("TRIAL-") and len(body["code"]) == 20
        row = TrialCode.objects.get()
        assert row.code_hash == trials.hash_of(body["code"])
        assert body["code"] not in str(vars(row))
        listed = boss.get(CODES).json()["codes"][0]
        assert "code" not in listed and listed["status"] == "unused"
        assert listed["plan"]["id"] == plan.pk and listed["days"] == 14 and listed["cv_limit"] == 50
        assert "admin.trial_code_created" in kinds()
        assert body["code"] not in str(AuditEvent.objects.last().details)

    def test_days_and_cvs_are_required_and_bounded_with_no_default(self, boss, plan):
        for change in ({"days": 0}, {"days": 91}, {"cv_limit": 0}, {"cv_limit": 10001}):
            assert boss.post(CODES, {**self_body(plan), **change}, format="json").status_code == 400
        missing = self_body(plan)
        del missing["cv_limit"]
        assert boss.post(CODES, missing, format="json").status_code == 400
        assert not TrialCode.objects.exists()

    def test_the_bounds_are_platform_settings(self, boss, plan):
        set_setting("trials.max_days", 5)
        assert boss.post(CODES, {**self_body(plan), "days": 6}, format="json").status_code == 400
        assert boss.post(CODES, {**self_body(plan), "days": 5}, format="json").status_code == 201

    def test_an_expiry_in_the_past_is_refused(self, boss, plan):
        past = (timezone.now() - timedelta(days=1)).isoformat()
        response = boss.post(CODES, {**self_body(plan), "expires_at": past}, format="json")
        assert response.status_code == 400

    def test_a_code_can_be_switched_off_and_on_with_an_audit_entry(self, boss, plan):
        new_code(boss, plan)
        row = TrialCode.objects.get()
        assert (
            boss.patch(f"{CODES}{row.pk}/", {"enabled": False}, format="json").json()["status"]
            == "off"
        )
        assert (
            boss.patch(f"{CODES}{row.pk}/", {"enabled": True}, format="json").json()["status"]
            == "unused"
        )
        assert kinds().count("admin.trial_code_switched") == 2
        assert boss.patch(f"{CODES}{row.pk}/", {"enabled": True}, format="json").status_code == 400
        assert boss.patch(f"{CODES}999/", {"enabled": True}, format="json").status_code == 404

    def test_only_super_admins_may_use_it(self, plan):
        support = client_for(make_admin_user(role="support"))
        assert support.get(CODES).status_code == 403
        assert support.post(CODES, self_body(plan), format="json").status_code == 403
        assert support.patch(f"{CODES}1/", {"enabled": False}, format="json").status_code == 403
        assert APIClient().get(CODES).status_code == 401
        assert not TrialCode.objects.exists()


def self_body(plan):
    return {
        "name": "Fake campaign",
        "plan_id": plan.pk,
        "days": 14,
        "cv_limit": 50,
        "expires_at": (timezone.now() + timedelta(days=30)).isoformat(),
    }


class TestRedeeming:
    def test_the_owner_starts_a_trial_with_the_codes_plan_days_and_cv_limit(
        self, boss, plan, company, owner
    ):
        code = new_code(boss, plan)["code"]
        response = owner.post(REDEEM, {"code": code}, format="json")
        assert response.status_code == 200, response.content
        subscription = sub(company)
        assert subscription.state == State.GRANTED_FREE and subscription.on_trial
        assert subscription.plan_id == plan.pk and subscription.trial_cv_limit == 50
        assert subscription.trial_started_at is not None and subscription.renewal is False
        days = (subscription.period_end - subscription.period_start).days
        assert days in (13, 14)
        body = response.json()
        assert body["cv_limit"] == 50 and body["cvs_used"] == 0
        row = TrialCode.objects.get()
        assert row.redeemed_company_id == company.pk and row.redeemed_at is not None
        assert "trial.code_redeemed" in kinds()
        assert OutgoingEmail.objects.filter(template="usage_notice").exists()

    def test_the_code_works_in_any_spelling(self, boss, plan, owner):
        code = new_code(boss, plan)["code"]
        sloppy = " " + code.lower().replace("-", " ") + " "
        assert owner.post(REDEEM, {"code": sloppy}, format="json").status_code == 200

    def test_a_code_can_be_used_by_one_company_only(self, boss, plan, owner):
        code = new_code(boss, plan)["code"]
        assert owner.post(REDEEM, {"code": code}, format="json").status_code == 200
        other = signed_in(make_company())[0]
        response = other.post(REDEEM, {"code": code}, format="json")
        assert response.status_code == 400 and response.json()["error"]["code"] == "code_not_usable"

    def test_every_unusable_code_gets_the_same_answer(self, boss, plan, owner):
        expired = new_code(boss, plan)["code"]
        TrialCode.objects.filter(code_hash=trials.hash_of(expired)).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        switched_off = new_code(boss, plan)["code"]
        TrialCode.objects.filter(code_hash=trials.hash_of(switched_off)).update(enabled=False)
        used = new_code(boss, plan)["code"]
        signed_in(make_company())[0].post(REDEEM, {"code": used}, format="json")
        answers = {
            owner.post(REDEEM, {"code": text}, format="json").content
            for text in (expired, switched_off, used, "TRIAL-NOPE-NOPE-NOPE", "x")
        }
        assert len(answers) == 1
        assert b"This code cannot be used." in answers.pop()

    def test_a_company_has_one_trial_ever(self, boss, plan, company, owner):
        first, second = new_code(boss, plan)["code"], new_code(boss, plan)["code"]
        assert owner.post(REDEEM, {"code": first}, format="json").status_code == 200
        Subscription.objects.filter(company=company).update(
            state=State.EXPIRED, on_trial=False, period_end=timezone.now()
        )
        response = owner.post(REDEEM, {"code": second}, format="json")
        assert response.status_code == 409 and response.json()["error"]["code"] == "trial_used"
        assert TrialCode.objects.get(code_hash=trials.hash_of(second)).redeemed_at is None

    def test_a_company_with_a_paid_plan_cannot_start_a_trial(self, boss, plan, company, owner):
        now = timezone.now()
        subs.activate(company.pk, plan, period_start=now, period_end=now + timedelta(days=30))
        code = new_code(boss, plan)["code"]
        assert owner.post(REDEEM, {"code": code}, format="json").status_code == 409
        assert TrialCode.objects.get().redeemed_at is None

    def test_only_the_owner_may_redeem(self, boss, plan, company):
        member = signed_in(company, role="member")[0]
        code = new_code(boss, plan)["code"]
        assert member.post(REDEEM, {"code": code}, format="json").status_code == 403
        assert APIClient().post(REDEEM, {"code": code}, format="json").status_code == 401
        assert TrialCode.objects.get().redeemed_at is None

    def test_tries_are_limited_per_company_right_or_wrong(self, boss, plan, owner):
        set_setting("rate_limits.code_attempts_per_hour", 3)
        codes = [
            owner.post(REDEEM, {"code": "TRIAL-NOPE"}, format="json").status_code for _ in range(4)
        ]
        assert codes == [400, 400, 400, 429]
        good = new_code(boss, plan)["code"]
        assert owner.post(REDEEM, {"code": good}, format="json").status_code == 429
        assert not TrialCode.objects.get().redeemed_at

    def test_another_company_has_its_own_allowance(self, owner):
        set_setting("rate_limits.code_attempts_per_hour", 1)
        owner.post(REDEEM, {"code": "x"}, format="json")
        other = signed_in(make_company())[0]
        assert other.post(REDEEM, {"code": "x"}, format="json").status_code == 400


class TestAdminTrial:
    def url(self, company):
        return f"/api/admin/companies/{company.pk}/subscription/trial/"

    def body(self, plan, **changes):
        return {"plan_id": plan.pk, "days": 10, "cv_limit": 20, "reason": REASON, **changes}

    def test_a_super_admin_starts_a_trial_with_a_reason(self, boss, plan, company):
        response = boss.post(self.url(company), self.body(plan), format="json")
        assert response.status_code == 200, response.content
        subscription = sub(company)
        assert subscription.on_trial and subscription.trial_cv_limit == 20
        event = AuditEvent.objects.get(kind="admin.trial_started")
        assert event.reason == REASON

    def test_a_reason_and_the_numbers_are_required(self, boss, plan, company):
        for change in ({"reason": ""}, {"days": 0}, {"cv_limit": 0}, {"days": 91}):
            assert (
                boss.post(self.url(company), self.body(plan, **change), format="json").status_code
                == 400
            )
        for name in ("days", "cv_limit", "reason"):
            body = self.body(plan)
            del body[name]
            assert boss.post(self.url(company), body, format="json").status_code == 400
        assert not sub(company).on_trial

    def test_support_is_refused(self, plan, company):
        support = client_for(make_admin_user(role="support"))
        assert support.post(self.url(company), self.body(plan), format="json").status_code == 403

    def test_one_trial_ever_for_the_company(self, boss, plan, company):
        boss.post(self.url(company), self.body(plan), format="json")
        boss.post(
            f"/api/admin/companies/{company.pk}/subscription/end-free/",
            {"reason": REASON},
            format="json",
        )
        again = boss.post(self.url(company), self.body(plan), format="json")
        assert again.status_code == 409 and again.json()["error"]["code"] == "trial_used"


class TestTheCvLimit:
    @pytest.fixture
    def trial(self, boss, plan, company):
        boss.post(
            f"/api/admin/companies/{company.pk}/subscription/trial/",
            {"plan_id": plan.pk, "days": 10, "cv_limit": 3, "reason": REASON},
            format="json",
        )
        return company

    def accept(self, company, count):
        for _ in range(count):
            usage.accept_cv(company.pk, uuid.uuid4())

    def test_cvs_fit_up_to_the_trials_limit(self, trial):
        self.accept(trial, 2)
        check = limits.check_cvs_this_month(trial.pk)
        assert check.allowed and check.room == 1 and check.limit == 3

    def test_the_limit_stops_processing_with_the_upgrade_prompt(self, trial):
        self.accept(trial, 3)
        check = limits.check_cvs_this_month(trial.pk)
        assert not check.allowed
        assert check.code == "trial_cv_limit_reached" and check.prompt == "upgrade"
        assert "3 CVs" in check.message

    def test_a_batch_is_cut_at_what_is_left_of_the_trial(self, trial):
        self.accept(trial, 1)
        split = limits.split_batch(trial.pk, ["a", "b", "c", "d"], 0)
        assert split.accepted == ["a", "b"]
        assert {item.code for item in split.skipped} == {"trial_cv_limit_reached"}

    def test_a_failed_cv_gives_its_place_back(self, trial):
        cv = uuid.uuid4()
        usage.accept_cv(trial.pk, cv)
        self.accept(trial, 2)
        assert not limits.check_cvs_this_month(trial.pk).allowed
        usage.mark_failed(trial.pk, cv)
        assert limits.check_cvs_this_month(trial.pk).allowed

    def test_the_plans_own_monthly_limit_still_applies_if_it_is_stricter(self, boss, company):
        small = make_plan(cvs_per_month=1)
        boss.post(
            f"/api/admin/companies/{company.pk}/subscription/trial/",
            {"plan_id": small.pk, "days": 10, "cv_limit": 50, "reason": REASON},
            format="json",
        )
        self.accept(company, 1)
        assert limits.check_cvs_this_month(company.pk).code == "monthly_cv_limit_reached"

    def test_a_company_without_a_trial_is_unchanged(self, company, plan):
        now = timezone.now()
        subs.activate(company.pk, plan, period_start=now, period_end=now + timedelta(days=30))
        assert limits.check_cvs_this_month(company.pk).limit == 100

    def test_the_usage_summary_shows_the_trial(self, trial):
        from plans.summary import plan_and_usage

        self.accept(trial, 1)
        summary = plan_and_usage(trial.pk)
        assert summary["trial"]["cv_limit"] == 3 and summary["trial"]["cvs_used"] == 1
        assert summary["cvs"]["limit"] == 3 and summary["cvs"]["used"] == 1


class TestTheEnd:
    @pytest.fixture
    def trial(self, boss, plan, company):
        boss.post(
            f"/api/admin/companies/{company.pk}/subscription/trial/",
            {"plan_id": plan.pk, "days": 5, "cv_limit": 10, "reason": REASON},
            format="json",
        )
        return company

    def test_after_its_days_the_company_can_only_view_and_download(self, trial):
        Subscription.objects.filter(company=trial).update(
            period_end=timezone.now() - timedelta(minutes=1)
        )
        assert subs.effective_state(sub(trial)) == State.EXPIRED
        assert subs.can_view(trial.pk) and not subs.can_upload(trial.pk)
        assert not limits.check_ai_allowed(trial.pk).allowed
        assert limits.check_cvs_this_month(trial.pk).prompt == "upgrade"  # nothing to renew

    def test_the_job_ends_it_audits_it_and_emails_the_owner_once(self, trial):
        make_company_user(trial)
        Subscription.objects.filter(company=trial).update(
            period_end=timezone.now() - timedelta(minutes=1)
        )
        subs.expire_lapsed_subscriptions()
        subscription = sub(trial)
        assert subscription.state == State.EXPIRED and not subscription.on_trial
        assert subscription.trial_started_at is not None  # one trial, ever
        assert "trial.ended" in kinds()

        def ended():
            return [
                mail
                for mail in OutgoingEmail.objects.filter(template="usage_notice")
                if "free trial has ended" in mail.text_body
            ]

        assert len(ended()) == 1
        assert "Nothing was deleted" in ended()[0].text_body
        subs.expire_lapsed_subscriptions()
        assert len(ended()) == 1

    def test_buying_a_plan_during_the_trial_starts_the_paid_month_and_drops_the_rest(
        self, trial, plan
    ):
        now = timezone.now()
        subs.activate(
            trial.pk, plan, period_start=now, period_end=now + timedelta(days=30),
            stripe_customer_id="cus_fake", stripe_subscription_id="sub_fake",
        )  # fmt: skip
        subscription = sub(trial)
        assert subscription.state == State.ACTIVE and not subscription.on_trial
        assert subscription.period_end > now + timedelta(days=29)
        assert limits.check_cvs_this_month(trial.pk).limit == 100

    def test_checkout_is_open_to_a_company_on_a_trial_but_not_to_a_paying_one(
        self, trial, plan, monkeypatch
    ):
        from plans import checkout

        calls = []
        monkeypatch.setattr(checkout, "require_details", lambda company_id: object())
        monkeypatch.setattr(checkout, "ensure_customer", lambda details: "cus_fake")

        class Session:
            id, url = "cs_fake", "https://pay.example.com/x"
            amount_total = 1000

        def fake_session(**kwargs):
            calls.append(kwargs)
            return Session()

        monkeypatch.setattr(checkout.stripe_client, "create_checkout_session", fake_session)
        assert checkout.start_checkout(trial.pk, plan.pk) == "https://pay.example.com/x"
        now = timezone.now()
        subs.activate(trial.pk, plan, period_start=now, period_end=now + timedelta(days=30))
        with pytest.raises(Exception) as caught:
            checkout.start_checkout(trial.pk, plan.pk)
        assert "already" in str(caught.value.message)


class TestEndingNotice:
    @pytest.fixture
    def trial(self, boss, plan, company):
        make_company_user(company)
        boss.post(
            f"/api/admin/companies/{company.pk}/subscription/trial/",
            {"plan_id": plan.pk, "days": 10, "cv_limit": 10, "reason": REASON},
            format="json",
        )
        return company

    def test_it_is_sent_three_days_before_the_end_and_only_once(self, trial):
        assert billing_notices.send_trial_ending_notices() == 0  # ten days left
        Subscription.objects.filter(company=trial).update(
            period_end=timezone.now() + timedelta(days=2)
        )
        assert billing_notices.send_trial_ending_notices() == 1
        assert billing_notices.send_trial_ending_notices() == 0
        assert OutgoingEmail.objects.filter(template="trial_ending").count() == 1

    def test_the_days_are_a_platform_setting(self, trial):
        Subscription.objects.filter(company=trial).update(
            period_end=timezone.now() + timedelta(days=5)
        )
        assert billing_notices.send_trial_ending_notices() == 0
        set_setting("trials.ending_notice_days", 7)
        assert billing_notices.send_trial_ending_notices() == 1

    def test_a_trial_does_not_also_get_the_ordinary_ending_notice(self, trial):
        Subscription.objects.filter(company=trial).update(
            period_end=timezone.now() + timedelta(days=2)
        )
        assert billing_notices.send_ending_notices() == 0

    def test_an_ordinary_free_grant_still_gets_the_ordinary_notice(self, boss, plan, company):
        make_company_user(company)
        subs.grant_free(
            company.pk, plan, period_end=timezone.now() + timedelta(days=2), by=None, reason=REASON
        )
        assert billing_notices.send_ending_notices() == 1
        assert billing_notices.send_trial_ending_notices() == 0

    def test_the_daily_job_is_scheduled(self):
        from django_q.models import Schedule

        assert Schedule.objects.filter(
            func="notifications.billing_notices.send_trial_ending_notices"
        ).exists()
