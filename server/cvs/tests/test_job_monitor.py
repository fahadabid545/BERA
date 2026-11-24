import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers.models import AdminUser
from ai import control
from ai.tests.test_model_settings import REASON, admin_client
from audit.models import AuditEvent
from core.tests.factories import make_admin_user, make_company, make_company_user
from cvs import job_monitor, processing
from cvs.models import CvFile
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from usage import service as usage
from usage.models import CvUsage, UsageCounter

pytestmark = pytest.mark.django_db
URL = "/api/admin/jobs/"
SECRET_NAME = "secret-candidate-name.pdf"


@pytest.fixture
def kicks(monkeypatch):
    asked = []
    monkeypatch.setattr(processing, "async_task", lambda job: asked.append(job))
    return asked


@pytest.fixture(autouse=True)
def restored_steps():
    """Tests that plug in their own steps leave the real ones as they found them."""
    real = dict(processing.STEPS)
    yield
    processing.STEPS.clear()
    processing.STEPS.update(real)


@pytest.fixture
def tenant():
    return Tenant(make_plan())


@pytest.fixture
def boss():
    return admin_client("super")[0]


def minutes_ago(minutes):
    return timezone.now() - timedelta(minutes=minutes)


def waiting(tenant, **fields):
    return tenant.cv(**fields)


def running(tenant, minutes=1, **fields):
    return tenant.cv(
        status="reading", started_at=minutes_ago(minutes), claim_token=uuid.uuid4(), attempts=1,
        **fields,
    )  # fmt: skip


def stuck(tenant, **fields):
    return running(tenant, minutes=30, **fields)


def failed(tenant, reason="We could not read this file.", name=None, **fields):
    row = tenant.cv(
        status="failed", failure_reason=reason, finished_at=timezone.now(), attempts=3, **fields
    )
    usage.mark_failed(tenant.company.pk, row.pk)
    if name:
        CvFile.objects.filter(pk=row.pk).update(original_name=name)
    return row


def reload(row):
    return CvFile.objects.get(pk=row.pk)


def entry(row):
    return CvUsage.objects.get(company_id=row.company_id, cv_id=row.pk)


def listing(client, **query):
    return client.get(URL, query)


def states(reply):
    return sorted(item["state"] for item in reply.json()["items"])


class TestTheList:
    def test_shows_waiting_running_failed_and_stuck_jobs_with_reasons(self, boss, tenant):
        waiting(tenant), running(tenant), stuck(tenant), failed(tenant, "Could not read it.")
        items = {item["state"]: item for item in listing(boss).json()["items"]}
        assert set(items) == {"waiting", "running", "stuck", "failed"}
        assert items["failed"]["reason"] == "Could not read it."
        assert items["waiting"]["reason"] == "Waiting for its turn."
        assert items["running"]["reason"] == "Being processed."
        assert items["stuck"]["reason"] == processing.TOO_LONG_REASON
        assert items["failed"]["project"] == "T"
        assert items["failed"]["company"] == tenant.company.name

    def test_each_job_says_what_can_be_done_with_it(self, boss, tenant):
        waiting(tenant), running(tenant), stuck(tenant), failed(tenant)
        can = {
            item["state"]: (item["can_retry"], item["can_cancel"])
            for item in listing(boss).json()["items"]
        }
        assert can == {
            "waiting": (False, True), "running": (False, False),
            "stuck": (True, True), "failed": (True, False),
        }  # fmt: skip

    def test_a_job_that_is_done_cancelled_or_awaiting_confirmation_is_not_listed(
        self, boss, tenant
    ):
        for status in ("done", "cancelled", "awaiting_confirmation"):
            tenant.cv(status=status)
        assert listing(boss).json()["items"] == []

    def test_the_stuck_time_is_the_platform_setting(self, boss, tenant):
        set_setting("processing.stuck_minutes", 20)
        running(tenant, minutes=10)
        assert states(listing(boss)) == ["running"]
        set_setting("processing.stuck_minutes", 5)
        assert states(listing(boss)) == ["stuck"]

    def test_a_retry_that_is_due_later_and_a_paused_ai_are_explained(self, boss, tenant):
        waiting(tenant, attempts=1)
        assert listing(boss).json()["items"][0]["reason"] == "Waiting to try again."
        control.pause(make_admin_user(email="pauser@example.test"), REASON)
        assert listing(boss).json()["items"][0]["reason"] == control.PAUSED_MESSAGE

    def test_jobs_are_grouped_by_company_with_counts(self, boss, tenant):
        other = Tenant(make_plan())
        waiting(tenant), failed(tenant), stuck(other)
        shown = listing(boss).json()
        counts = {entry["id"]: entry for entry in shown["companies"]}
        assert counts[str(tenant.company.pk)]["waiting"] == 1
        assert counts[str(tenant.company.pk)]["failed"] == 1
        assert counts[str(other.company.pk)]["stuck"] == 1
        assert shown["totals"] == {"waiting": 1, "running": 0, "failed": 1, "stuck": 1}
        names = [item["company"] for item in shown["items"]]
        assert names == sorted(names, key=str.casefold)  # one company's jobs sit together
        assert [name for name in names if name == tenant.company.name] == [tenant.company.name] * 2

    def test_a_company_with_no_jobs_is_not_listed(self, boss, tenant):
        make_company()
        assert listing(boss).json()["companies"] == []

    def test_can_be_filtered_by_state_and_by_company(self, boss, tenant):
        other = Tenant(make_plan())
        waiting(tenant), failed(tenant), failed(other)
        assert states(listing(boss, state="failed")) == ["failed", "failed"]
        only = listing(boss, company=str(other.company.pk)).json()
        assert [item["state"] for item in only["items"]] == ["failed"]
        assert only["total"] == 1
        assert states(listing(boss, state="waiting", company=str(other.company.pk))) == []

    def test_a_filter_that_makes_no_sense_is_refused(self, boss, tenant):
        assert listing(boss, state="done").status_code == 400
        assert listing(boss, company="not-an-id").status_code == 400
        assert listing(boss, extra="1").status_code == 400

    def test_at_most_the_limit_is_listed_with_the_real_total(self, boss, tenant):
        set_setting("admin_jobs.list_limit", 10)
        for _ in range(12):
            waiting(tenant)
        shown = listing(boss).json()
        assert (len(shown["items"]), shown["total"]) == (10, 12)

    def test_no_file_name_or_candidate_content_is_shown(self, boss, tenant):
        failed(tenant, name=SECRET_NAME)
        assert SECRET_NAME not in listing(boss).content.decode()


class TestWhoMayUseIt:
    def test_support_may_list_retry_and_cancel(self, tenant, kicks):
        support = admin_client("support")[0]
        retry, cancel = failed(tenant), waiting(tenant)
        assert listing(support).status_code == 200
        assert support.post(f"{URL}{retry.pk}/retry/").status_code == 200
        assert support.post(f"{URL}{cancel.pk}/cancel/").status_code == 200

    def test_a_company_user_is_refused(self, tenant):
        row = failed(tenant)
        member = tenant.client
        assert member.get(URL).status_code in (401, 403)
        assert member.post(f"{URL}{row.pk}/retry/").status_code in (401, 403)
        assert member.post(f"{URL}{row.pk}/cancel/").status_code in (401, 403)
        assert reload(row).status == "failed"

    def test_someone_not_signed_in_is_refused(self, tenant):
        row = failed(tenant)
        assert APIClient().get(URL).status_code == 401
        assert APIClient().post(f"{URL}{row.pk}/retry/").status_code == 401
        assert APIClient().post(f"{URL}{row.pk}/cancel/").status_code == 401
        assert reload(row).status == "failed"


class TestRetry:
    def test_a_failed_job_goes_back_in_line_and_waits_for_the_month_again(
        self, boss, tenant, kicks
    ):
        row = failed(tenant)
        assert usage.waiting_cvs(tenant.company.pk) == 0
        assert boss.post(f"{URL}{row.pk}/retry/").status_code == 200
        row = reload(row)
        assert (row.status, row.attempts, row.failure_reason) == ("waiting", 0, "")
        assert row.finished_at is None and row.ai_failure is False
        assert usage.waiting_cvs(tenant.company.pk) == 1
        assert len(kicks) == 1

    def test_the_retry_is_audited_with_the_company(self, boss, tenant, kicks):
        row = failed(tenant)
        boss.post(f"{URL}{row.pk}/retry/")
        event = AuditEvent.objects.get(kind="admin.job_retried")
        assert event.company_id == tenant.company.pk
        assert event.details == {"job_id": str(row.pk), "was": "failed"}

    def test_retrying_twice_never_repeats_anything(self, boss, tenant, kicks):
        row = failed(tenant)
        assert boss.post(f"{URL}{row.pk}/retry/").status_code == 200
        again = boss.post(f"{URL}{row.pk}/retry/")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "job_not_retryable"
        assert CvFile.objects.count() == 1 and CvUsage.objects.count() == 1
        assert usage.waiting_cvs(tenant.company.pk) == 1
        assert AuditEvent.objects.filter(kind="admin.job_retried").count() == 1
        assert len(kicks) == 1

    def test_a_retried_job_is_counted_once_when_it_is_scored(self, boss, tenant, kicks):
        processing.STEPS.clear()
        processing.register_step(
            "scoring", lambda ctx: usage.mark_scored(ctx.company_id, ctx.cv_file.pk)
        )
        row = failed(tenant)
        boss.post(f"{URL}{row.pk}/retry/")
        processing.tick()
        assert reload(row).status == "done"
        assert UsageCounter.objects.get(company=tenant.company).cvs_scored == 1
        assert boss.post(f"{URL}{row.pk}/retry/").status_code == 409  # done: nothing to retry
        assert UsageCounter.objects.get(company=tenant.company).cvs_scored == 1

    def test_a_failed_job_already_counted_is_not_counted_again(self, boss, tenant, kicks):
        """A failed re-scoring of a counted CV: it stays counted, and a retry adds nothing."""
        processing.STEPS.clear()
        processing.register_step(
            "scoring", lambda ctx: usage.mark_scored(ctx.company_id, ctx.cv_file.pk)
        )
        row = tenant.cv()
        usage.mark_scored(tenant.company.pk, row.pk)
        CvFile.objects.filter(pk=row.pk).update(status="failed", failure_reason="x", attempts=3)
        boss.post(f"{URL}{row.pk}/retry/")
        assert entry(row).status == "scored"
        processing.tick()
        assert UsageCounter.objects.get(company=tenant.company).cvs_scored == 1

    def test_a_stuck_job_goes_back_in_line_with_fresh_tries(self, boss, tenant, kicks):
        row = stuck(tenant)
        old_worker = reload(row)
        assert boss.post(f"{URL}{row.pk}/retry/").status_code == 200
        row = reload(row)
        assert (row.status, row.attempts, row.claim_token, row.started_at) == (
            "waiting", 0, None, None,
        )  # fmt: skip
        assert len(kicks) == 1
        # the worker that held it can no longer change it
        assert processing._holds(old_worker).update(status="done") == 0
        assert reload(row).status == "waiting"
        assert AuditEvent.objects.get(kind="admin.job_retried").details["was"] == "stuck"

    def test_retrying_a_stuck_job_leaves_its_usage_alone(self, boss, tenant, kicks):
        row = stuck(tenant)
        before = (entry(row).status, usage.waiting_cvs(tenant.company.pk))
        boss.post(f"{URL}{row.pk}/retry/")
        assert (entry(row).status, usage.waiting_cvs(tenant.company.pk)) == before
        assert CvUsage.objects.count() == 1

    @pytest.mark.parametrize("make", [waiting, running])
    def test_a_job_that_is_waiting_or_running_cannot_be_retried(self, boss, tenant, make):
        row = make(tenant)
        reply = boss.post(f"{URL}{row.pk}/retry/")
        assert reply.status_code == 409
        assert reply.json()["error"]["message"] == "Only a failed or stuck job can be retried."
        assert reload(row).status == row.status

    @pytest.mark.parametrize("status", ["done", "cancelled", "awaiting_confirmation"])
    def test_a_job_that_is_not_background_work_cannot_be_retried(self, boss, tenant, status):
        row = tenant.cv(status=status)
        assert boss.post(f"{URL}{row.pk}/retry/").status_code == 409

    def test_a_job_that_no_longer_fits_the_month_stays_failed(self, boss, kicks):
        tenant = Tenant(make_plan(cvs_per_month=1))
        counted = tenant.cv()
        usage.mark_scored(tenant.company.pk, counted.pk)
        row = failed(tenant)
        reply = boss.post(f"{URL}{row.pk}/retry/")
        assert reply.status_code == 409
        assert reload(row).status == "failed"
        assert entry(row).status == "failed"
        assert kicks == []

    def test_an_unknown_job_is_not_found(self, boss):
        assert boss.post(f"{URL}{uuid.uuid4()}/retry/").status_code == 404
        assert boss.post(f"{URL}not-an-id/retry/").status_code == 404


class TestCancel:
    def test_a_waiting_job_is_cancelled_and_gives_its_allowance_back(self, boss, tenant):
        row = waiting(tenant)
        assert usage.waiting_cvs(tenant.company.pk) == 1
        assert boss.post(f"{URL}{row.pk}/cancel/").status_code == 200
        row = reload(row)
        assert row.status == "cancelled" and row.finished_at and row.claim_token is None
        assert usage.waiting_cvs(tenant.company.pk) == 0
        assert entry(row).status == "failed"  # never counted
        assert UsageCounter.objects.filter(company=tenant.company, cvs_scored__gt=0).count() == 0

    def test_the_cancel_is_audited_with_the_company(self, boss, tenant):
        row = waiting(tenant)
        boss.post(f"{URL}{row.pk}/cancel/")
        event = AuditEvent.objects.get(kind="admin.job_cancelled")
        assert event.company_id == tenant.company.pk
        assert event.details == {"job_id": str(row.pk), "was": "waiting"}

    def test_a_stuck_job_is_cancelled_and_its_worker_loses_it(self, boss, tenant):
        row = stuck(tenant)
        old_worker = reload(row)
        assert boss.post(f"{URL}{row.pk}/cancel/").status_code == 200
        assert reload(row).status == "cancelled"
        assert processing._holds(old_worker).update(status="done") == 0
        assert usage.waiting_cvs(tenant.company.pk) == 0

    def test_a_cancelled_job_is_never_picked_up(self, boss, tenant):
        row = waiting(tenant)
        boss.post(f"{URL}{row.pk}/cancel/")
        assert processing.claim_next() is None
        assert reload(row).status == "cancelled"

    def test_cancelling_twice_changes_nothing_the_second_time(self, boss, tenant):
        row = waiting(tenant)
        boss.post(f"{URL}{row.pk}/cancel/")
        again = boss.post(f"{URL}{row.pk}/cancel/")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "job_not_cancellable"
        assert AuditEvent.objects.filter(kind="admin.job_cancelled").count() == 1
        assert CvUsage.objects.count() == 1

    @pytest.mark.parametrize("make", [running, failed])
    def test_running_and_failed_jobs_cannot_be_cancelled(self, boss, tenant, make):
        row = make(tenant)
        reply = boss.post(f"{URL}{row.pk}/cancel/")
        assert reply.status_code == 409
        assert reply.json()["error"]["message"] == "Only a waiting or stuck job can be cancelled."
        assert reload(row).status == row.status

    def test_a_job_that_is_done_cannot_be_cancelled(self, boss, tenant):
        row = tenant.cv(status="done")
        assert boss.post(f"{URL}{row.pk}/cancel/").status_code == 409

    def test_an_unknown_job_is_not_found(self, boss):
        assert boss.post(f"{URL}{uuid.uuid4()}/cancel/").status_code == 404


class TestTheAttentionTab:
    def pending(self, client):
        return client.get("/api/admin/dashboard/").json()["pending"]

    def test_failed_jobs_are_counted_for_both_roles(self, boss, tenant):
        failed(tenant), failed(tenant), waiting(tenant), stuck(tenant)
        assert self.pending(boss)["failed_jobs"] == 2
        assert self.pending(admin_client("support")[0])["failed_jobs"] == 2

    def test_a_retried_or_cancelled_job_leaves_the_count(self, boss, tenant, kicks):
        row = failed(tenant)
        boss.post(f"{URL}{row.pk}/retry/")
        assert self.pending(boss)["failed_jobs"] == 0

    def test_review_lists_the_failed_jobs_with_company_and_reason(self, boss, tenant):
        failed(tenant, "Could not read it.", name=SECRET_NAME)
        waiting(tenant)
        reply = boss.get("/api/admin/dashboard/detail/", {"kind": "pending", "key": "failed_jobs"})
        body = reply.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["type"] == "job" and item["company"] == tenant.company.name
        assert item["company_id"] == str(tenant.company.pk)
        assert item["reason"] == "Could not read it."
        assert SECRET_NAME not in reply.content.decode()

    def test_the_review_is_open_to_support_too(self, tenant):
        failed(tenant)
        support = admin_client("support")[0]
        reply = support.get(
            "/api/admin/dashboard/detail/", {"kind": "pending", "key": "failed_jobs"}
        )
        assert reply.status_code == 200 and reply.json()["total"] == 1


def test_the_monitor_names_the_states_it_lists():
    assert job_monitor.STATES == ("waiting", "running", "failed", "stuck")
    assert AdminUser.Role.SUPER and make_company_user  # the roles and factories are in use
