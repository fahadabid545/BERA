"""Emails that follow the work and the subscription: each goes once, to the right people, and
the optional ones can be switched off by each person."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from django_q.models import Schedule
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for
from cvs import processing
from cvs.models import CvFile
from cvs.tests.test_processing import Tenant, make_plan
from emailing.models import OutgoingEmail
from notifications import billing_notices, progress
from notifications.kinds import KINDS
from notifications.models import NotificationChoice, NotificationSent
from notifications.service import set_choice
from plans import subscriptions as subs
from usage import service as usage
from usage.models import UsageCounter

pytestmark = pytest.mark.django_db

URL = "/api/company/notifications/"
ALLOWANCE = "allowance"


@pytest.fixture
def tenant(monkeypatch):
    monkeypatch.setattr(processing, "STEPS", {})  # no real steps: a CV goes straight to done
    return Tenant(make_plan(cvs_per_month=10))


def mails(template, text=None):
    found = OutgoingEmail.objects.filter(template=template)
    return [mail for mail in found if text is None or text in mail.text_body]


def finish_next():
    processing.run_item(processing.claim_next())


class TestFinishedUploads:
    def test_it_goes_to_the_uploader_when_the_last_cv_is_done(self, tenant):
        batch = uuid.uuid4()
        tenant.cv(batch=batch)
        tenant.cv(batch=batch)
        finish_next()
        assert mails("batch_finished") == []
        finish_next()
        (mail,) = mails("batch_finished")
        assert mail.to_address == tenant.owner.email
        assert "2 CVs were scored" in mail.text_body
        assert f"/company/projects/{tenant.project.pk}" in mail.text_body

    def test_a_failed_cv_is_counted_in_the_words(self, tenant, monkeypatch):
        batch = uuid.uuid4()
        tenant.cv(batch=batch)
        tenant.cv(batch=batch, status="failed")
        finish_next()
        (mail,) = mails("batch_finished")
        assert "1 CV was scored and 1 CV could not be read" in mail.text_body

    def test_a_cancelled_upload_says_nothing(self, tenant):
        batch = uuid.uuid4()
        tenant.cv(batch=batch)
        processing.cancel_unstarted(tenant.project, batch)
        assert mails("batch_finished") == []

    def test_cancelling_what_is_left_finishes_the_upload(self, tenant):
        batch = uuid.uuid4()
        tenant.cv(batch=batch)
        tenant.cv(batch=batch)
        finish_next()
        processing.cancel_unstarted(tenant.project, batch)
        assert len(mails("batch_finished")) == 1

    def test_a_retried_cv_does_not_send_a_second_email(self, tenant):
        batch = uuid.uuid4()
        row = tenant.cv(batch=batch)
        finish_next()
        CvFile.objects.filter(pk=row.pk).update(status="waiting", next_attempt_at=timezone.now())
        finish_next()
        assert len(mails("batch_finished")) == 1

    def test_each_upload_has_its_own_email(self, tenant):
        for _ in range(2):
            tenant.cv(batch=uuid.uuid4())
            finish_next()
        assert len(mails("batch_finished")) == 2

    def test_a_person_who_switched_it_off_gets_none(self, tenant):
        set_choice(tenant.owner, "batch_finished", False)
        tenant.cv(batch=uuid.uuid4())
        finish_next()
        assert mails("batch_finished") == []

    def test_a_problem_sending_never_stops_the_cv(self, tenant, monkeypatch):
        def broken(*args, **kwargs):
            raise RuntimeError("no mail")

        monkeypatch.setattr("notifications.progress.notify", broken)
        row = tenant.cv(batch=uuid.uuid4())
        finish_next()
        row.refresh_from_db()
        assert row.status == "done"


def score(tenant, count):
    for _ in range(count):
        cv_id = uuid.uuid4()
        usage.accept_cv(tenant.company.pk, cv_id)
        usage.mark_scored(tenant.company.pk, cv_id)


class TestUsage:
    def test_nothing_goes_before_the_first_level(self, tenant):
        score(tenant, 7)
        assert mails("usage_notice", ALLOWANCE) == []

    def test_eighty_percent_goes_once_to_the_owner(self, tenant):
        score(tenant, 8)
        score(tenant, 1)
        (mail,) = mails("usage_notice", ALLOWANCE)
        assert mail.to_address == tenant.owner.email
        assert "80%" in mail.text_body and "8 of 10" in mail.text_body

    def test_the_full_allowance_goes_once_more(self, tenant):
        score(tenant, 8)
        score(tenant, 2)
        score(tenant, 0)
        texts = [mail.text_body for mail in mails("usage_notice", ALLOWANCE)]
        assert len(texts) == 2
        assert "reached its monthly CV allowance" in texts[1]

    def test_a_jump_over_a_level_sends_one_email_for_the_highest(self, tenant):
        cv_id = uuid.uuid4()
        entry = usage.accept_cv(tenant.company.pk, cv_id)
        UsageCounter.objects.create(
            company=tenant.company, period=entry.period, project_id=None, cvs_scored=10
        )
        progress.usage_reached(tenant.company.pk)
        (mail,) = mails("usage_notice", ALLOWANCE)
        assert "reached" in mail.text_body
        assert NotificationSent.objects.filter(kind="usage_warning").exists()  # marked, not sent

    def test_the_next_period_warns_again(self, tenant):
        score(tenant, 8)
        NotificationSent.objects.all().delete()  # what a new period's keys amount to
        score(tenant, 1)
        assert len(mails("usage_notice", ALLOWANCE)) == 2

    def test_a_company_without_an_allowance_has_nothing_to_measure(self):
        tenant = Tenant(make_plan(cvs_per_month=0))
        score(tenant, 3)
        assert mails("usage_notice", ALLOWANCE) == []

    def test_each_level_can_be_switched_off_on_its_own(self, tenant):
        set_choice(tenant.owner, "usage_warning", False)
        score(tenant, 8)
        assert mails("usage_notice", ALLOWANCE) == []
        score(tenant, 2)
        (mail,) = mails("usage_notice", ALLOWANCE)
        assert "reached" in mail.text_body

    def test_a_switched_off_level_is_not_sent_later_either(self, tenant):
        set_choice(tenant.owner, "usage_warning", False)
        score(tenant, 8)
        set_choice(tenant.owner, "usage_warning", True)
        score(tenant, 1)
        assert mails("usage_notice", ALLOWANCE) == []


class TestSubscriptionEnding:
    def activate(self, tenant, days, renewal=False):
        now = timezone.now()
        subs.activate(
            tenant.company.pk,
            tenant.plan,
            period_start=now - timedelta(days=20),
            period_end=now + timedelta(days=days),
            renewal=renewal,
        )

    @pytest.fixture
    def tenant(self):
        made = Tenant(make_plan())
        made.plan = made.company.pk and subs.get_subscription(made.company.pk).plan
        return made

    def test_it_goes_seven_days_before_and_only_once(self, tenant):
        self.activate(tenant, 6)
        assert billing_notices.send_ending_notices() == 1
        assert billing_notices.send_ending_notices() == 0
        (mail,) = mails("subscription_ending")
        assert mail.to_address == tenant.owner.email
        assert "/company/billing" in mail.text_body

    def test_it_waits_until_the_seven_days(self, tenant):
        self.activate(tenant, 9)
        assert billing_notices.send_ending_notices() == 0
        assert mails("subscription_ending") == []

    def test_a_renewing_subscription_is_not_ending(self, tenant):
        self.activate(tenant, 3, renewal=True)
        billing_notices.send_ending_notices()
        assert mails("subscription_ending") == []

    def test_a_cancelled_subscription_is_ending(self, tenant):
        self.activate(tenant, 3, renewal=True)
        subs.cancel(tenant.company.pk)
        billing_notices.send_ending_notices()
        assert len(mails("subscription_ending")) == 1

    def test_a_free_grant_is_ending_too(self):
        tenant = Tenant(make_plan())
        plan = subs.get_subscription(tenant.company.pk).plan
        subs.expire(tenant.company.pk)
        subs.grant_free(
            tenant.company.pk,
            plan,
            period_end=timezone.now() + timedelta(days=2),
            by=None,
            reason="trial",
        )
        billing_notices.send_ending_notices()
        assert len(mails("subscription_ending")) == 1

    def test_a_subscription_that_already_ended_gets_nothing(self, tenant):
        self.activate(tenant, -1)
        assert billing_notices.send_ending_notices() == 0

    def test_a_new_end_date_is_a_new_occasion(self, tenant):
        self.activate(tenant, 3)
        billing_notices.send_ending_notices()
        self.activate(tenant, 4)
        billing_notices.send_ending_notices()
        assert len(mails("subscription_ending")) == 2

    def test_a_suspended_company_is_skipped(self, tenant):
        self.activate(tenant, 3)
        tenant.company.status = "suspended"
        tenant.company.save()
        assert billing_notices.send_ending_notices() == 0

    def test_it_cannot_be_switched_off(self, tenant):
        NotificationChoice.objects.create(
            company=tenant.company, user=tenant.owner, kind="subscription_ending", enabled=False
        )
        self.activate(tenant, 3)
        billing_notices.send_ending_notices()
        assert len(mails("subscription_ending")) == 1

    def test_the_daily_job_is_scheduled(self):
        job = Schedule.objects.get(func="notifications.billing_notices.send_ending_notices")
        assert job.schedule_type == "D"


class TestPaymentFailed:
    @pytest.fixture
    def paid(self):
        tenant = Tenant(make_plan())
        return tenant

    def test_it_goes_once_when_the_payment_fails(self, paid):
        subs.mark_past_due(paid.company.pk)
        (mail,) = mails("payment_problem")
        assert mail.to_address == paid.owner.email
        assert "could not take your payment" in mail.text_body
        assert "/company/billing" in mail.text_body

    def test_a_second_failure_after_paying_is_a_new_email(self, paid):
        plan = subs.get_subscription(paid.company.pk).plan
        now = timezone.now()
        subs.mark_past_due(paid.company.pk)
        subs.activate(paid.company.pk, plan, period_start=now, period_end=now + timedelta(days=30))
        subs.mark_past_due(paid.company.pk)
        assert len(mails("payment_problem")) == 2

    def test_it_cannot_be_switched_off(self, paid):
        NotificationChoice.objects.create(
            company=paid.company, user=paid.owner, kind="payment_failed", enabled=False
        )
        subs.mark_past_due(paid.company.pk)
        assert len(mails("payment_problem")) == 1


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


class TestChoices:
    def test_every_kind_is_listed_and_required_ones_say_so(self):
        _, client = sign_in(make_company())
        body = client.get(URL).json()["choices"]
        assert [row["kind"] for row in body] == [kind.name for kind in KINDS]
        required = {row["kind"] for row in body if row["required"]}
        assert required == {"subscription_ending", "payment_failed"}
        assert all(row["enabled"] for row in body)

    def test_an_optional_email_can_be_switched_off_and_on(self):
        person, client = sign_in(make_company())
        reply = client.patch(URL, {"kind": "batch_finished", "enabled": False}, format="json")
        assert reply.status_code == 200
        shown = {row["kind"]: row["enabled"] for row in reply.json()["choices"]}
        assert shown["batch_finished"] is False
        client.patch(URL, {"kind": "batch_finished", "enabled": True}, format="json")
        assert NotificationChoice.objects.get(user=person).enabled is True

    def test_a_required_email_cannot_be_switched_off(self):
        person, client = sign_in(make_company())
        reply = client.patch(URL, {"kind": "payment_failed", "enabled": False}, format="json")
        assert reply.status_code == 409
        assert reply.json()["error"]["code"] == "notification_required"
        assert not NotificationChoice.objects.filter(user=person).exists()

    def test_an_unknown_kind_is_not_found(self):
        _, client = sign_in(make_company())
        reply = client.patch(URL, {"kind": "nonsense", "enabled": False}, format="json")
        assert reply.status_code == 404

    def test_a_missing_value_is_a_form_mistake(self):
        _, client = sign_in(make_company())
        assert client.patch(URL, {"kind": "batch_finished"}, format="json").status_code == 400

    def test_signing_in_is_needed(self):
        assert APIClient().get(URL).status_code == 401

    def test_each_person_has_their_own_choices(self):
        company = make_company()
        _, mine = sign_in(company)
        _, theirs = sign_in(company, role="member")
        mine.patch(URL, {"kind": "batch_finished", "enabled": False}, format="json")
        other = {row["kind"]: row["enabled"] for row in theirs.get(URL).json()["choices"]}
        assert other["batch_finished"] is True

    def test_another_company_cannot_see_or_change_them(self):
        _, mine = sign_in(make_company())
        person, theirs = sign_in(make_company())
        mine.patch(URL, {"kind": "batch_finished", "enabled": False}, format="json")
        assert NotificationChoice.objects.exclude(user=person).count() == 1
        shown = {row["kind"]: row["enabled"] for row in theirs.get(URL).json()["choices"]}
        assert shown["batch_finished"] is True
