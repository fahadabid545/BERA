from datetime import timedelta

import pytest
from django.utils import timezone

from ai import control
from ai.client import AiPaused, AiUnavailable
from ai.models import AiControl
from ai.tests.test_model_settings import REASON, admin_client
from core.tests.factories import make_admin_user
from cvs import processing
from cvs.models import CvFile
from cvs.processing import register_step
from cvs.tests.test_processing import Tenant, advance, make_plan
from usage import service as usage

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan():
    return make_plan()


@pytest.fixture
def tenant(plan):
    return Tenant(plan)


@pytest.fixture(autouse=True)
def clean_steps(monkeypatch):
    real = dict(processing.STEPS)
    processing.STEPS.clear()
    asked = []
    monkeypatch.setattr(processing, "async_task", lambda job: asked.append(job))
    yield asked
    processing.STEPS.clear()
    processing.STEPS.update(real)


@pytest.fixture
def kicks(clean_steps):
    return clean_steps


@pytest.fixture
def clock(monkeypatch):
    """A clock the test can move."""
    state = {"now": timezone.now()}
    monkeypatch.setattr(processing, "_now", lambda: state["now"])
    return state


def reload(row):
    return CvFile.objects.get(pk=row.pk)


def always_down(context):
    raise AiUnavailable("down")


def fail_for_good(tenant, clock):
    """A CV whose AI never answers, run through all its tries."""
    register_step("text_reading", always_down)
    row = tenant.cv()
    for _ in range(3):
        item = processing.claim_next()
        processing.run_item(item)
        advance(clock, minutes=10)
    return reload(row)


class TestRetriesThenALaterRetry:
    def test_a_cv_the_ai_never_answers_is_tried_three_times_with_waits(self, tenant, clock):
        register_step("text_reading", always_down)
        row = tenant.cv()
        item = processing.claim_next()
        processing.run_item(item)
        first = reload(row)
        assert (first.status, first.attempts) == ("waiting", 1)
        assert first.next_attempt_at > clock["now"]  # it waits before the next try
        assert processing.claim_next() is None
        advance(clock, minutes=10)
        processing.run_item(processing.claim_next())
        advance(clock, minutes=10)
        processing.run_item(processing.claim_next())
        assert (reload(row).status, reload(row).attempts) == ("failed", 3)

    def test_it_is_then_marked_as_failed_by_the_ai_with_a_plain_reason(self, tenant, clock):
        row = fail_for_good(tenant, clock)
        assert row.ai_failure is True
        assert (
            row.failure_reason
            == "The AI service could not be reached. This will be tried again when it is back."
        )

    def test_another_kind_of_failure_is_not_marked_as_the_ais(self, tenant, clock):
        def broken(context):
            raise ValueError("secret detail")

        register_step("text_reading", broken)
        row = tenant.cv()
        for _ in range(3):
            processing.run_item(processing.claim_next())
            advance(clock, minutes=10)
        assert (reload(row).status, reload(row).ai_failure) == ("failed", False)

    def test_failed_items_are_not_counted_against_the_limits(self, tenant, clock):
        row = fail_for_good(tenant, clock)
        assert row.status == "failed"
        assert usage.waiting_cvs(tenant.company.pk) == 0
        assert usage.current_usage(tenant.company.pk)["cvs_scored"] == 0
        assert usage.current_usage(tenant.company.pk)["tokens_in"] == 0

    def test_a_cv_already_counted_stays_counted_when_its_later_work_fails(self, tenant, clock):
        row = tenant.cv()
        usage.mark_scored(tenant.company.pk, row.pk)
        CvFile.objects.filter(pk=row.pk).update(status="waiting")
        register_step("text_reading", always_down)
        for _ in range(3):
            processing.run_item(processing.claim_next())
            advance(clock, minutes=10)
        assert usage.current_usage(tenant.company.pk)["cvs_scored"] == 1


class TestWhilePaused:
    def test_nothing_is_picked_up_and_no_try_is_used(self, tenant, kicks):
        row = tenant.cv()
        AiControl.objects.update_or_create(pk=1, defaults={"paused": True})
        assert processing.claim_next() is None
        processing.tick()
        assert (reload(row).status, reload(row).attempts) == ("waiting", 0)

    def test_after_resuming_the_waiting_cvs_go_in_their_original_order(self, tenant, kicks):
        first, second, third = tenant.cv(), tenant.cv(), tenant.cv()
        AiControl.objects.update_or_create(pk=1, defaults={"paused": True})
        assert processing.claim_next() is None
        boss, admin = admin_client("super")
        boss.post("/api/admin/ai/controls/resume/", {"reason": REASON}, format="json")
        order = [processing.claim_next().pk for _ in range(3)]
        assert order == [first.pk, second.pk, third.pk]

    def test_a_cv_in_flight_when_the_pause_starts_goes_back_without_losing_a_try(self, tenant):
        def paused_midway(context):
            raise AiPaused("paused")

        register_step("text_reading", paused_midway)
        row = tenant.cv()
        item = processing.claim_next()
        assert item.attempts == 1
        processing.run_item(item)
        back = reload(row)
        assert (back.status, back.attempts, back.failure_reason) == ("waiting", 0, "")
        assert back.claim_token is None

    def test_a_pause_never_fails_a_cv(self, tenant):
        register_step("text_reading", lambda c: (_ for _ in ()).throw(AiPaused("paused")))
        row = tenant.cv()
        for _ in range(5):
            processing.run_item(processing.claim_next())
        assert reload(row).status == "waiting"

    def test_the_project_page_tells_users_ai_is_paused(self, tenant):
        tenant.cv()
        url = f"/api/company/projects/{tenant.project.pk}/processing/"
        assert tenant.client.get(url).json()["ai_paused"] is False
        AiControl.objects.update_or_create(pk=1, defaults={"paused": True})
        body = tenant.client.get(url).json()
        assert body["ai_paused"] is True
        assert body["ai_paused_message"] == "AI scoring is paused. We will resume automatically."

    def test_requirement_suggestions_say_so_instead_of_failing(self, tenant, monkeypatch):
        AiControl.objects.update_or_create(pk=1, defaults={"paused": True})
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/requirements/suggest/"
        )
        body = response.json()
        assert body["fallback"] is True
        assert body["message"] == "AI scoring is paused. We will resume automatically."


class TestResuming:
    def test_the_cvs_that_failed_because_of_the_ai_go_back_in_line_when_it_resumes(
        self, tenant, clock, kicks
    ):
        row = fail_for_good(tenant, clock)
        boss, _ = admin_client("super")
        boss.post("/api/admin/ai/controls/resume/", {"reason": REASON}, format="json")
        back = reload(row)
        assert (back.status, back.attempts, back.failure_reason, back.ai_failure) == (
            "waiting", 0, "", False,
        )  # fmt: skip
        assert usage.waiting_cvs(tenant.company.pk) == 1
        assert kicks

    def test_other_failures_stay_failed_for_the_manual_retry(self, tenant, kicks):
        unreadable = tenant.cv(status="failed", failure_reason="We could not read this file.")
        control.resume(make_admin_user(role="super"), REASON)
        assert reload(unreadable).status == "failed"

    def test_the_sweep_ends_an_expired_automatic_pause_and_puts_the_cvs_back(
        self, tenant, clock, kicks
    ):
        row = fail_for_good(tenant, clock)
        AiControl.objects.update_or_create(
            pk=1, defaults={"auto_paused_until": clock["now"] - timedelta(seconds=1)}
        )
        processing.sweep()
        assert reload(row).status == "waiting"
        assert control.is_paused() is False

    def test_the_sweep_leaves_a_pause_that_is_not_over(self, tenant, clock, kicks):
        row = fail_for_good(tenant, clock)
        AiControl.objects.update_or_create(
            pk=1, defaults={"auto_paused_until": clock["now"] + timedelta(minutes=5)}
        )
        processing.sweep()
        assert reload(row).status == "failed" and control.is_paused() is True

    def test_a_cv_that_no_longer_fits_the_months_limit_stays_failed(self, tenant, clock, kicks):
        row = fail_for_good(tenant, clock)
        other = tenant.cv()  # the month is now full with this one
        from plans.models import Plan

        Plan.objects.update(cvs_per_month=1)
        control.resume(make_admin_user(role="super"), REASON)
        assert reload(row).status == "failed" and reload(other).status == "waiting"

    def test_an_archived_project_is_not_touched(self, tenant, clock, kicks):
        from projects.service import archive_project

        row = fail_for_good(tenant, clock)
        archive_project(tenant.project.pk, tenant.company.pk)
        control.resume(make_admin_user(role="super"), REASON)
        assert reload(row).status == "failed"

    def test_oldest_failures_go_first(self, tenant, clock, kicks):
        first = fail_for_good(tenant, clock)
        advance(clock, minutes=5)
        register_step("text_reading", always_down)
        second = tenant.cv()
        for _ in range(3):
            processing.run_item(processing.claim_next())
            advance(clock, minutes=10)
        control.resume(make_admin_user(role="super"), REASON)
        order = [processing.claim_next().pk for _ in range(2)]
        assert order == [first.pk, second.pk]


def test_the_set_up_ends_with_the_hook_registered():
    assert processing.retry_after_outage in control._RESUME_HOOKS
