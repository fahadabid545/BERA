import threading
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone
from django_q.models import Schedule
from rest_framework.test import APIClient

from core import periodic
from core.rate_limits import BlockedSource, RateCounter
from core.tests.factories import make_company, make_company_user, start_session_for
from cvs import duplicates, processing
from cvs.models import CvFile, ProcessingTurn
from cvs.processing import PermanentFailure, register_step
from cvs.tests.files import make_pdf
from plans import subscriptions as subs
from plans.models import Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project
from usage import service as usage

pytestmark = pytest.mark.django_db

EXPECTED_STEPS = {
    "text_reading",
    "ai_reading",
    "fairness_guard",
}  # a ticket that plugs in a step adds its slot here


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


def make_plan(**changes):
    return Plan.objects.create(
        **{
            "name": "Basic",
            "status": "active",
            "price_usd": 10,
            "cvs_per_month": 100,
            "cvs_per_project": 50,
            "max_projects": 5,
            "max_team_accounts": 3,
            "max_top_n": 10,
            "monthly_ai_token_cap": 10000,
            **changes,
        }
    )


class Tenant:
    """A company with an owner, a project and a signed-in client."""

    def __init__(self, plan):
        self.company = make_company()
        now = timezone.now()
        subs.activate(self.company.pk, plan, period_start=now, period_end=now + timedelta(days=30))
        self.owner = make_company_user(self.company)
        issued = start_session_for(
            user_id=self.owner.pk, role="owner", company_id=self.company.pk, kind="company"
        )
        self.client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        self.project = Project.objects.create(
            company=self.company,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=self.owner,
        )
        self.counter = 0

    def cv(self, status="waiting", batch=None, project=None, **fields):
        """A CV row as an upload leaves it (the file itself is not needed by fake steps)."""
        self.counter += 1
        project = project or self.project
        fields.setdefault("next_attempt_at", processing._now())
        row = CvFile.objects.create(
            company=self.company,
            project=project,
            original_name=f"cv{self.counter}.pdf",
            file_type="pdf",
            size_bytes=1,
            storage_key=f"cvs/{self.company.pk}/fake-{self.counter}-{id(self)}",
            uploaded_by=self.owner,
            status=status,
            batch_id=batch,
            content_hash=f"{self.company.pk}-{self.counter}-{id(self)}",
            **fields,
        )
        usage.accept_cv(self.company.pk, row.pk, project.pk)
        return row

    def upload(self, *files, batch=None):
        sent = [SimpleUploadedFile(name, data) for name, data in files]
        body = {"files": sent, **({"batch": str(batch)} if batch else {})}
        return self.client.post(
            f"/api/company/projects/{self.project.pk}/cvs/", body, format="multipart"
        )


@pytest.fixture
def plan():
    return make_plan()


@pytest.fixture
def tenant(plan):
    return Tenant(plan)


@pytest.fixture(autouse=True)
def clean_steps():
    """Each test starts with no steps (and gets the real ones back afterwards)."""
    real = dict(processing.STEPS)
    processing.STEPS.clear()
    yield
    processing.STEPS.clear()
    processing.STEPS.update(real)


@pytest.fixture
def kicks(monkeypatch):
    asked = []
    monkeypatch.setattr(processing, "async_task", lambda job: asked.append(job))
    return asked


@pytest.fixture
def clock(monkeypatch):
    """A clock the test can move."""
    state = {"now": timezone.now()}
    monkeypatch.setattr(processing, "_now", lambda: state["now"])
    return state


def advance(clock, **delta):
    clock["now"] += timedelta(**delta)


def reload(row):
    return CvFile.objects.get(pk=row.pk)


class TestSlots:
    def test_the_slots_are_named_and_ordered(self):
        assert processing.SLOTS == ("text_reading", "ai_reading", "fairness_guard", "scoring")

    def test_the_steps_plugged_in_so_far_are_exactly_the_expected_ones(self):
        import importlib

        from cvs import fairness, profile_reading, steps

        importlib.reload(steps)
        importlib.reload(profile_reading)
        importlib.reload(fairness)
        assert set(processing.STEPS) == EXPECTED_STEPS

    def test_an_unknown_slot_fails_loudly(self):
        with pytest.raises(KeyError):
            register_step("nonsense", lambda context: None)

    def test_with_no_steps_every_slot_is_skipped_and_the_cv_is_done(self, tenant, kicks):
        row = tenant.cv()
        item = processing.claim_next()
        processing.run_item(item)
        assert reload(row).status == "done"
        assert reload(row).claim_token is None

    def test_steps_run_in_slot_order_and_share_what_they_learn(self, tenant):
        seen = []
        register_step("scoring", lambda c: seen.append(("scoring", c.state["text"])))
        register_step(
            "text_reading", lambda c: c.state.update(text="the text") or seen.append("text")
        )
        register_step("fairness_guard", lambda c: seen.append(("guard", c.state["text"])))
        tenant.cv()
        processing.run_item(processing.claim_next())
        assert seen == ["text", ("guard", "the text"), ("scoring", "the text")]

    def test_the_status_follows_the_slot_being_run(self, tenant):
        row = tenant.cv()
        statuses = {}
        for slot in processing.SLOTS:
            register_step(slot, lambda c, slot=slot: statuses.update({slot: reload(row).status}))
        processing.run_item(processing.claim_next())
        assert statuses == {
            "text_reading": "reading",
            "ai_reading": "reading",
            "fairness_guard": "reading",
            "scoring": "scoring",
        }
        assert reload(row).status == "done"


class TestRetriesAndFailure:
    def boom(self, context):
        raise RuntimeError("secret CV text and a stack trace")

    def test_a_hiccup_waits_and_is_tried_again_later(self, tenant, clock):
        register_step("text_reading", self.boom)
        row = tenant.cv()
        processing.run_item(processing.claim_next())
        row = reload(row)
        assert (row.status, row.attempts) == ("waiting", 1)
        assert row.next_attempt_at == clock["now"] + timedelta(seconds=30)
        assert processing.claim_next() is None  # not due yet
        advance(clock, seconds=31)
        assert processing.claim_next().pk == row.pk

    def test_it_fails_for_good_after_three_tries_with_longer_waits(self, tenant, clock):
        register_step("text_reading", self.boom)
        row = tenant.cv()
        waits = []
        for _ in range(3):
            advance(clock, seconds=200)
            processing.run_item(processing.claim_next())
            waits.append(reload(row).next_attempt_at - clock["now"])
        row = reload(row)
        assert (row.status, row.attempts) == ("failed", 3)
        assert waits[:2] == [timedelta(seconds=30), timedelta(seconds=120)]
        assert row.failure_reason == processing.GAVE_UP_REASON
        assert row.finished_at is not None

    def test_the_failure_reason_leaks_nothing(self, tenant, clock):
        register_step("text_reading", self.boom)
        row = tenant.cv()
        for _ in range(3):
            advance(clock, seconds=200)
            processing.run_item(processing.claim_next())
        assert "secret" not in reload(row).failure_reason
        assert "stack" not in reload(row).failure_reason

    def test_a_failed_cv_is_not_counted_and_gives_its_allowance_back(self, tenant, clock):
        register_step("text_reading", self.boom)
        row = tenant.cv()
        assert usage.waiting_cvs(tenant.company.pk) == 1
        for _ in range(3):
            advance(clock, seconds=200)
            processing.run_item(processing.claim_next())
        assert usage.waiting_cvs(tenant.company.pk) == 0
        assert usage.current_usage(tenant.company.pk)["cvs_scored"] == 0
        assert reload(row).status == "failed"

    def test_a_file_that_cannot_be_processed_fails_at_once_with_its_reason(self, tenant):
        def unreadable(context):
            raise PermanentFailure("We could not read this file.")

        register_step("text_reading", unreadable)
        row = tenant.cv()
        processing.run_item(processing.claim_next())
        row = reload(row)
        assert (row.status, row.attempts) == ("failed", 1)
        assert row.failure_reason == "We could not read this file."
        assert usage.waiting_cvs(tenant.company.pk) == 0

    def test_the_number_of_tries_and_the_waits_come_from_platform_settings(self, tenant, clock):
        set_setting("processing.max_attempts", 2)
        set_setting("processing.retry_waits_seconds", [7])
        register_step("text_reading", self.boom)
        row = tenant.cv()
        processing.run_item(processing.claim_next())
        assert reload(row).next_attempt_at == clock["now"] + timedelta(seconds=7)
        advance(clock, seconds=8)
        processing.run_item(processing.claim_next())
        assert reload(row).status == "failed"

    def test_a_step_that_works_on_the_second_try_finishes(self, tenant, clock):
        calls = []

        def flaky(context):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("hiccup")

        register_step("text_reading", flaky)
        row = tenant.cv()
        processing.run_item(processing.claim_next())
        advance(clock, seconds=40)
        processing.run_item(processing.claim_next())
        assert (reload(row).status, reload(row).attempts) == ("done", 2)

    def test_the_log_names_the_kind_of_error_but_not_its_message(self, tenant, caplog):
        register_step("text_reading", self.boom)
        tenant.cv()
        with caplog.at_level("ERROR"):
            processing.run_item(processing.claim_next())
        assert "RuntimeError" in caplog.text
        assert "secret CV text" not in caplog.text


class TestFairness:
    def test_companies_take_turns_so_a_large_batch_cannot_hold_others_up(self, plan):
        big, small, tiny = Tenant(plan), Tenant(plan), Tenant(plan)
        for _ in range(8):
            big.cv()
        for _ in range(2):
            small.cv()
        tiny.cv()
        order = []
        while (item := processing.claim_next()) is not None:
            order.append(item.company_id)
            processing.run_item(item)
        big_id, small_id, tiny_id = big.company.pk, small.company.pk, tiny.company.pk
        assert set(order[:3]) == {big_id, small_id, tiny_id}  # everyone is served first
        assert order.index(tiny_id) < 3
        last_of_small = max(index for index, company in enumerate(order) if company == small_id)
        assert last_of_small < 6  # not queued behind the eight
        assert order.count(big_id) == 8

    def test_within_a_company_the_oldest_cv_goes_first(self, tenant):
        first, second = tenant.cv(), tenant.cv()
        assert processing.claim_next().pk == first.pk
        assert processing.claim_next().pk == second.pk

    def test_a_company_that_waited_longer_goes_before_one_served_just_now(self, plan):
        a, b = Tenant(plan), Tenant(plan)
        a.cv(), a.cv(), b.cv(), b.cv()
        first = processing.claim_next()
        second = processing.claim_next()
        assert {first.company_id, second.company_id} == {a.company.pk, b.company.pk}

    def test_each_claim_records_the_companys_turn(self, tenant):
        tenant.cv()
        processing.claim_next()
        assert ProcessingTurn.objects.get(company=tenant.company).last_served_at

    def test_cvs_still_waiting_for_their_retry_are_not_claimed(self, tenant, clock):
        tenant.cv(next_attempt_at=clock["now"] + timedelta(minutes=5))
        assert processing.claim_next() is None


class TestNothingRunsTwiceOrIsLost:
    def test_a_cv_is_claimed_by_one_worker_only(self, tenant):
        tenant.cv()
        first = processing.claim_next()
        assert first is not None
        assert processing.claim_next() is None

    def test_a_claim_gives_the_cv_a_fresh_token_and_counts_the_try(self, tenant):
        row = tenant.cv()
        item = processing.claim_next()
        assert item.claim_token is not None and item.attempts == 1 and item.status == "reading"
        assert reload(row).claim_token == item.claim_token

    def test_a_worker_that_was_replaced_cannot_change_the_cv_or_run_its_steps(self, tenant, clock):
        ran = []
        register_step("text_reading", lambda c: ran.append(1))
        row = tenant.cv()
        old = processing.claim_next()
        advance(clock, minutes=6)
        processing.sweep()  # the first worker is taken to be dead
        advance(clock, seconds=31)  # and the CV waits a little before its next try
        new = processing.claim_next()
        assert new.claim_token != old.claim_token
        processing.run_item(old)  # the old worker wakes up and carries on
        assert ran == []
        assert reload(row).claim_token == new.claim_token
        assert reload(row).status == "reading"

    def test_a_late_failure_from_a_replaced_worker_changes_nothing(self, tenant, clock):
        register_step("text_reading", lambda c: (_ for _ in ()).throw(PermanentFailure("late")))
        row = tenant.cv()
        old = processing.claim_next()
        advance(clock, minutes=6)
        processing.sweep()
        advance(clock, seconds=31)
        processing.claim_next()
        processing.run_item(old)
        assert reload(row).status == "reading"
        assert usage.waiting_cvs(tenant.company.pk) == 1

    @pytest.mark.django_db(transaction=True)
    def test_two_workers_at_the_same_moment_never_get_the_same_cv(self, plan):
        tenant = Tenant(plan)
        tenant.cv()
        got, barrier = [], threading.Barrier(2)

        def worker():
            try:
                barrier.wait()
                got.append(processing.claim_next())
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(item is not None for item in got) == [False, True]

    def test_the_cvs_are_in_the_database_so_a_restart_loses_none(self, tenant, kicks):
        rows = [tenant.cv() for _ in range(3)]
        # "Restart": the queue of tasks is gone; the rows are what counts.
        processing.sweep()
        assert kicks == [processing.TICK_JOB] * 2  # as many as there are workers
        assert {row.pk for row in CvFile.objects.filter(status="waiting")} == {r.pk for r in rows}

    def test_a_cv_that_was_mid_try_during_a_restart_is_tried_again_after_five_minutes(
        self, tenant, clock, kicks
    ):
        row = tenant.cv()
        processing.claim_next()  # the worker dies here
        advance(clock, minutes=4)
        processing.sweep()
        assert reload(row).status == "reading"  # not stuck yet
        advance(clock, minutes=2)
        processing.sweep()
        row = reload(row)
        assert row.status == "waiting" and row.claim_token is None
        assert row.next_attempt_at > clock["now"]

    def test_the_stuck_time_comes_from_platform_settings(self, tenant, clock):
        set_setting("processing.stuck_minutes", 1)
        row = tenant.cv()
        processing.claim_next()
        advance(clock, seconds=90)
        processing.sweep()
        assert reload(row).status == "waiting"

    def test_a_cv_that_keeps_getting_stuck_fails_after_its_tries(self, tenant, clock):
        row = tenant.cv()
        for _ in range(3):
            advance(clock, seconds=200)
            processing.claim_next()
            advance(clock, minutes=6)
            processing.sweep()
        row = reload(row)
        assert row.status == "failed"
        assert row.failure_reason == processing.TOO_LONG_REASON
        assert usage.waiting_cvs(tenant.company.pk) == 0

    def test_the_sweep_wakes_no_more_workers_than_there_are(self, tenant, kicks):
        for _ in range(10):
            tenant.cv()
        processing.sweep()
        assert len(kicks) == 2  # Q_CLUSTER workers

    def test_the_sweep_with_nothing_waiting_wakes_nobody(self, tenant, kicks):
        processing.sweep()
        assert kicks == []

    def test_a_tick_does_one_cv_and_asks_for_the_next_while_more_are_due(self, tenant, kicks):
        tenant.cv(), tenant.cv()
        processing.tick()
        assert CvFile.objects.filter(status="done").count() == 1
        assert kicks == [processing.TICK_JOB]
        processing.tick()
        assert CvFile.objects.filter(status="done").count() == 2
        assert kicks == [processing.TICK_JOB]  # nothing more to ask for

    def test_a_tick_with_nothing_to_do_returns(self, tenant, kicks):
        processing.tick()
        assert kicks == []

    def test_if_the_queue_is_down_the_upload_still_works_and_the_sweep_finds_the_cv(
        self, tenant, monkeypatch
    ):
        def down(job):
            raise ConnectionError("queue unreachable")

        monkeypatch.setattr(processing, "async_task", down)
        response = tenant.upload(("a.pdf", make_pdf(text="Experienced engineer one")))
        assert response.json()["results"][0]["status"] == "accepted"
        assert CvFile.objects.filter(status="waiting").count() == 1


class TestCancelling:
    def test_cancelling_skips_what_has_not_started_and_gives_the_allowance_back(
        self, tenant, kicks
    ):
        running, waiting_a, waiting_b = tenant.cv(), tenant.cv(), tenant.cv()
        item = processing.claim_next()
        assert item.pk == running.pk
        assert processing.cancel_unstarted(tenant.project) == 2
        assert reload(waiting_a).status == reload(waiting_b).status == "cancelled"
        assert reload(running).status == "reading"  # already started: it finishes
        assert usage.waiting_cvs(tenant.company.pk) == 1
        assert processing.claim_next() is None  # cancelled items are never picked up

    def test_only_the_chosen_upload_is_cancelled(self, tenant):
        import uuid

        first, second = uuid.uuid4(), uuid.uuid4()
        a, b = tenant.cv(batch=first), tenant.cv(batch=second)
        assert processing.cancel_unstarted(tenant.project, first) == 1
        assert (reload(a).status, reload(b).status) == ("cancelled", "waiting")

    def test_done_and_failed_cvs_are_left_alone(self, tenant):
        done, failed = tenant.cv(status="done"), tenant.cv(status="failed")
        assert processing.cancel_unstarted(tenant.project) == 0
        assert (reload(done).status, reload(failed).status) == ("done", "failed")

    def test_another_project_or_company_is_never_touched(self, plan, tenant):
        other_project = Project.objects.create(
            company=tenant.company,
            title="O",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=tenant.owner,
        )
        stranger = Tenant(plan)
        elsewhere, theirs = tenant.cv(project=other_project), stranger.cv()
        tenant.cv()
        processing.cancel_unstarted(tenant.project)
        assert (reload(elsewhere).status, reload(theirs).status) == ("waiting", "waiting")

    def test_the_api_cancels_and_reports_how_many(self, tenant):
        tenant.cv(), tenant.cv()
        response = tenant.client.post(f"/api/company/projects/{tenant.project.pk}/cvs/cancel/", {})
        assert (response.status_code, response.json()) == (200, {"skipped": 2})

    def test_the_api_can_cancel_one_upload(self, tenant):
        import uuid

        batch = uuid.uuid4()
        tenant.cv(batch=batch), tenant.cv()
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/cvs/cancel/",
            {"batch": str(batch)},
            format="json",
        )
        assert response.json() == {"skipped": 1}

    def test_another_companys_project_is_not_found(self, plan, tenant):
        stranger = Tenant(plan)
        stranger.cv()
        response = tenant.client.post(
            f"/api/company/projects/{stranger.project.pk}/cvs/cancel/", {}
        )
        assert response.status_code == 404
        assert CvFile.objects.filter(status="cancelled").count() == 0


class TestRetryingAFailedCv:
    def test_a_failed_cv_goes_back_in_line_and_counts_again(self, tenant, kicks):
        row = tenant.cv()
        processing._give_up_for_test = None
        item = processing.claim_next()
        processing._give_up(item, "No luck.", timezone.now())
        assert usage.waiting_cvs(tenant.company.pk) == 0
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/cvs/{row.pk}/retry/"
        )
        assert response.status_code == 200
        row = reload(row)
        assert (row.status, row.attempts, row.failure_reason) == ("waiting", 0, "")
        assert usage.waiting_cvs(tenant.company.pk) == 1
        assert kicks == [processing.TICK_JOB]

    def test_a_cv_that_is_not_failed_cannot_be_retried(self, tenant):
        row = tenant.cv()
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/cvs/{row.pk}/retry/"
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "not_failed"

    def test_with_no_room_left_the_upgrade_prompt_shows(self, plan, tenant):
        Plan.objects.update(cvs_per_month=1)
        make_plan(name="Bigger", price_usd=99, cvs_per_month=500)
        failed = tenant.cv()
        item = processing.claim_next()
        processing._give_up(item, "No luck.", timezone.now())
        tenant.cv()  # takes the one place there is
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/cvs/{failed.pk}/retry/"
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"]["prompt"] == "upgrade"
        assert reload(failed).status == "failed"

    def test_an_archived_project_cannot_retry(self, tenant):
        row = tenant.cv(status="failed")
        Project.objects.filter(pk=tenant.project.pk).update(status="archived")
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/cvs/{row.pk}/retry/"
        )
        assert response.json()["error"]["code"] == "project_archived"

    def test_a_cv_cannot_be_retried_through_another_project(self, tenant):
        other = Project.objects.create(
            company=tenant.company,
            title="O",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=tenant.owner,
        )
        row = tenant.cv(status="failed")
        response = tenant.client.post(f"/api/company/projects/{other.pk}/cvs/{row.pk}/retry/")
        assert response.status_code == 404

    def test_another_companys_cv_is_not_found(self, plan, tenant):
        stranger = Tenant(plan)
        theirs = stranger.cv(status="failed")
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/cvs/{theirs.pk}/retry/"
        )
        assert response.status_code == 404
        assert reload(theirs).status == "failed"

    def test_a_member_may_retry(self, tenant, kicks):
        row = tenant.cv()
        processing._give_up(processing.claim_next(), "No luck.", timezone.now())
        issued = start_session_for(
            user_id=make_company_user(tenant.company, role="member").pk,
            role="member",
            company_id=tenant.company.pk,
            kind="company",
        )
        member = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        response = member.post(f"/api/company/projects/{tenant.project.pk}/cvs/{row.pk}/retry/")
        assert response.status_code == 200


class TestWhatTheProjectPageShows:
    def url(self, tenant):
        return f"/api/company/projects/{tenant.project.pk}/processing/"

    def test_counts_and_each_cvs_status_with_the_reason_for_a_failure(self, tenant):
        tenant.cv(), tenant.cv(status="reading"), tenant.cv(status="done")
        tenant.cv(status="failed", failure_reason="We could not read this file.")
        body = tenant.client.get(self.url(tenant)).json()
        assert body["counts"] == {
            "waiting": 1,
            "reading": 1,
            "scoring": 0,
            "done": 1,
            "failed": 1,
            "cancelled": 0,
        }
        failed = [item for item in body["items"] if item["status"] == "failed"][0]
        assert failed["reason"] == "We could not read this file."
        assert failed["can_retry"] is True
        assert all(
            item["can_retry"] is False for item in body["items"] if item["status"] != "failed"
        )
        assert set(failed) == {"id", "name", "status", "reason", "can_retry"}

    def test_the_page_is_told_how_often_to_look_again(self, tenant):
        assert tenant.client.get(self.url(tenant)).json()["refresh_seconds"] == 3

    def test_only_this_projects_cvs_are_listed(self, plan, tenant):
        stranger = Tenant(plan)
        stranger.cv()
        tenant.cv()
        assert len(tenant.client.get(self.url(tenant)).json()["items"]) == 1

    def test_the_list_is_limited_but_the_counts_are_complete(self, tenant):
        set_setting("processing.list_limit", 10)
        for _ in range(12):
            tenant.cv()
        body = tenant.client.get(self.url(tenant)).json()
        assert len(body["items"]) == 10 and body["counts"]["waiting"] == 12

    def test_another_companys_project_is_not_found(self, plan, tenant):
        stranger = Tenant(plan)
        assert tenant.client.get(self.url(stranger)).status_code == 404

    def test_nobody_signed_in_is_refused(self, tenant):
        assert APIClient().get(self.url(tenant)).status_code == 401


class TestUploadHandsOverToProcessing:
    def test_accepted_files_wake_the_workers_once_each(self, tenant, kicks):
        tenant.upload(
            ("a.pdf", make_pdf(text="Engineer one")), ("b.pdf", make_pdf(text="Engineer two"))
        )
        assert kicks == [processing.TICK_JOB] * 2

    def test_files_of_one_drop_share_a_batch_id(self, tenant, kicks):
        import uuid

        batch = uuid.uuid4()
        tenant.upload(
            ("a.pdf", make_pdf(text="Engineer one")),
            ("b.pdf", make_pdf(text="Engineer two")),
            batch=batch,
        )
        assert {row.batch_id for row in CvFile.objects.all()} == {batch}

    def test_a_request_without_a_batch_gets_its_own(self, tenant, kicks):
        tenant.upload(("a.pdf", make_pdf(text="Engineer one")))
        assert CvFile.objects.get().batch_id is not None

    def test_nothing_accepted_wakes_nobody(self, tenant, kicks):
        tenant.upload(("notes.txt", b"hello"))
        assert kicks == []


class TestTheTextReadingStepEndToEnd:
    @pytest.fixture(autouse=True)
    def real_steps(self):
        from cvs import steps

        register_step("text_reading", steps.read_the_text)

    def test_an_uploaded_cv_is_read_and_done(self, tenant, kicks):
        tenant.upload(("a.pdf", make_pdf(text="Experienced engineer who builds payment systems")))
        processing.tick()
        assert CvFile.objects.get().status == "done"

    def test_a_cv_with_no_readable_text_fails_at_once_and_is_not_counted(self, tenant, kicks):
        import io

        from docx import Document

        buffer = io.BytesIO()
        Document().save(buffer)
        tenant.upload(("empty.docx", buffer.getvalue()))
        processing.tick()
        row = CvFile.objects.get()
        assert (row.status, row.attempts, row.failure_reason) == (
            "failed",
            1,
            "We could not read this file.",
        )
        assert usage.waiting_cvs(tenant.company.pk) == 0

    def test_a_missing_file_fails_with_a_clear_reason(self, tenant, kicks, settings):
        tenant.upload(("a.pdf", make_pdf(text="Experienced engineer who builds systems")))
        import privatefiles

        privatefiles.delete_file(CvFile.objects.get().storage_key)
        processing.tick()
        assert CvFile.objects.get().failure_reason == (
            "This file could not be found. Please upload it again."
        )

    def test_the_same_email_in_two_cvs_of_one_project_flags_the_later_one(self, tenant, kicks):
        import io

        from docx import Document

        def word(text):
            document = Document()
            document.add_paragraph(text)
            buffer = io.BytesIO()
            document.save(buffer)
            return buffer.getvalue()

        tenant.upload(
            ("a.docx", word("Jane Doe, jane@example.com, backend engineer with many years")),
            ("b.docx", word("J. Doe, jane@example.com, senior developer with many years")),
        )
        processing.tick()
        processing.tick()
        reviews = sorted(CvFile.objects.values_list("review", flat=True))
        assert reviews == ["flagged", "none"]


class TestJobsRunForTheRightCompany:
    def test_each_step_sees_only_its_own_companys_cv_and_project(self, plan):
        companies = [Tenant(plan) for _ in range(3)]
        seen = []
        register_step(
            "text_reading",
            lambda c: seen.append(
                (c.company_id, c.cv_file.company_id, c.project_id, c.cv_file.project.company_id)
            ),
        )
        for tenant in companies:
            tenant.cv(), tenant.cv()
        while (item := processing.claim_next()) is not None:
            processing.run_item(item)
        assert len(seen) == 6
        for company_id, cv_company, _project_id, project_company in seen:
            assert company_id == cv_company == project_company
        assert {row[2] for row in seen} == {t.project.pk for t in companies}

    def test_the_same_email_in_two_companies_is_never_taken_for_a_duplicate(self, plan):
        a, b = Tenant(plan), Tenant(plan)
        one, two = a.cv(), b.cv()
        duplicates.review_likely_duplicate(one, "jane@example.com")
        assert duplicates.review_likely_duplicate(two, "jane@example.com") is None

    def test_a_task_carries_no_data_only_the_instruction_to_look_for_work(
        self, tenant, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            processing, "async_task", lambda *args, **kwargs: calls.append((args, kwargs))
        )
        tenant.upload(("a.pdf", make_pdf(text="Experienced engineer one")))
        assert calls == [((processing.TICK_JOB,), {})]


class TestDeletingAProjectWhileItIsProcessed:
    def test_the_work_is_stopped_first_and_a_late_worker_changes_nothing(self, tenant, kicks):
        ran = []
        register_step("text_reading", lambda c: ran.append(1))
        tenant.cv(), tenant.cv()
        busy = processing.claim_next()
        response = tenant.client.delete(
            f"/api/company/projects/{tenant.project.pk}/", {"confirm_title": "T"}, format="json"
        )
        assert response.status_code == 204
        assert not CvFile.objects.exists()
        processing.run_item(busy)  # the worker that was busy wakes up afterwards
        assert ran == []
        assert processing.claim_next() is None

    def test_a_cvs_that_never_started_are_not_picked_up_after_the_deletion(self, tenant):
        tenant.cv()
        tenant.client.delete(
            f"/api/company/projects/{tenant.project.pk}/", {"confirm_title": "T"}, format="json"
        )
        assert processing.claim_next() is None


class TestScheduledJobs:
    def test_old_rate_limit_counters_are_cleared_once_a_day(self):
        schedule = Schedule.objects.get(func="core.periodic.purge_rate_limit_counters")
        assert schedule.schedule_type == Schedule.DAILY
        assert schedule.repeats == -1

    def test_the_processing_sweep_runs_every_minute(self):
        schedule = Schedule.objects.get(func="cvs.processing.sweep")
        assert (schedule.schedule_type, schedule.minutes, schedule.repeats) == (
            Schedule.MINUTES,
            1,
            -1,
        )

    def test_the_scheduled_jobs_exist_exactly_once(self):
        for func in ("core.periodic.purge_rate_limit_counters", "cvs.processing.sweep"):
            assert Schedule.objects.filter(func=func).count() == 1

    def test_the_daily_job_really_clears_old_counters(self):
        RateCounter.objects.create(key="old", window_start=1, count=3)
        BlockedSource.objects.create(key="gone", blocked_until=timezone.now() - timedelta(days=1))
        periodic.purge_rate_limit_counters()
        assert not RateCounter.objects.filter(key="old").exists()
        assert not BlockedSource.objects.filter(key="gone").exists()

    def test_the_daily_job_is_wrapped_so_a_failure_leaks_no_data(self, monkeypatch):
        from core.errors import AppError

        monkeypatch.setattr(periodic.rate_limits, "purge_old_counters", lambda: 1 / 0)
        with pytest.raises(AppError) as caught:
            periodic.purge_rate_limit_counters()
        assert caught.value.code == "job_failed"
