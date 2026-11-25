"""Many batches at once (BERA-111 and BERA-116 change): every batch moves along together, whoever
sent it, nothing leaks between companies while they run, and a busy AI provider never fails a
file. The AI is faked: the steps only count, so these run in a moment."""

import threading
import uuid
from collections import Counter
from datetime import timedelta

import pytest
from django.utils import timezone

from ai.client import AiBusy
from core.tests.factories import make_company_user
from cvs import processing
from cvs.models import CvFile
from cvs.processing import register_step
from cvs.tests.test_processing import Tenant, make_plan
from usage import service as usage

pytestmark = pytest.mark.django_db

BATCH_SIZE = 30


@pytest.fixture
def plan():
    return make_plan(cvs_per_month=1000, cvs_per_project=500)


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    """No real steps and no real queue: a step that only notes which batch it served."""
    real = dict(processing.STEPS)
    processing.STEPS.clear()
    monkeypatch.setattr(processing, "async_task", lambda job: None)
    yield
    processing.STEPS.clear()
    processing.STEPS.update(real)


def add_batch(tenant, uploader=None):
    batch = uuid.uuid4()
    for _ in range(BATCH_SIZE):
        row = tenant.cv(batch=batch)
        if uploader:
            CvFile.objects.filter(pk=row.pk).update(uploaded_by=uploader)
    return batch


def run_all(on_step=None):
    """What the workers do, one CV at a time. Returns the batch of each claim, in order."""
    order = []
    while (item := processing.claim_next()) is not None:
        order.append(item.batch_id)
        processing.run_item(item)
        if on_step:
            on_step(len(order))
    return order


def done_per_batch(batches):
    done = Counter(
        CvFile.objects.filter(batch_id__in=batches, status="done").values_list(
            "batch_id", flat=True
        )
    )
    return [done[batch] for batch in batches]


def assert_together(order, batches):
    """Round robin: every batch is served once in every round, so none waits for another."""
    assert set(order[: len(batches)]) == set(batches)  # all started before any could finish
    for start in range(0, len(order), len(batches)):
        assert Counter(order[start : start + len(batches)]) == Counter(batches)


class TestBatchesShareTheWorkers:
    def test_five_companies_with_30_files_each_progress_together(self, plan):
        tenants = [Tenant(plan) for _ in range(5)]
        batches = [add_batch(tenant) for tenant in tenants]
        paces = []
        order = run_all(lambda steps: paces.append(done_per_batch(batches)))
        assert_together(order, batches)
        assert all(max(pace) - min(pace) <= 1 for pace in paces)  # similar pace all along
        assert done_per_batch(batches) == [BATCH_SIZE] * 5
        # no batch finished before another had really begun
        assert all(max(pace) < BATCH_SIZE for pace in paces[: BATCH_SIZE * 4])

    def test_three_people_of_one_company_progress_together(self, plan):
        tenant = Tenant(plan)
        people = [make_company_user(tenant.company, role="member") for _ in range(3)]
        batches = [add_batch(tenant, person) for person in people]
        paces = []
        order = run_all(lambda steps: paces.append(done_per_batch(batches)))
        assert_together(order, batches)
        assert all(max(pace) - min(pace) <= 1 for pace in paces)
        assert done_per_batch(batches) == [BATCH_SIZE] * 3

    def test_a_batch_that_arrives_later_starts_at_once(self, plan):
        first, second = Tenant(plan), Tenant(plan)
        add_batch(first)
        for _ in range(10):  # the early batch is well under way
            processing.run_item(processing.claim_next())
        late = add_batch(second)
        assert processing.claim_next().batch_id == late

    def test_the_results_of_a_batch_appear_as_its_own_files_finish(self, plan):
        tenant = Tenant(plan)
        batches = [add_batch(tenant), add_batch(tenant)]
        for _ in range(4):
            processing.run_item(processing.claim_next())
        assert done_per_batch(batches) == [2, 2]


class TestEachCompanySeesOnlyItsOwnWhileRunning:
    def test_counts_and_files_stay_with_their_company_at_every_step(self, plan):
        tenants = [Tenant(plan) for _ in range(3)]
        batches = [add_batch(tenant) for tenant in tenants]
        own_ids = {
            tenant.company.pk: {
                str(pk)
                for pk in CvFile.objects.filter(company=tenant.company).values_list("pk", flat=True)
            }
            for tenant in tenants
        }

        def check(steps):
            if steps % 15:
                return
            for index, tenant in enumerate(tenants):
                reply = tenant.client.get(f"/api/company/projects/{tenant.project.pk}/processing/")
                assert reply.status_code == 200
                body = reply.json()
                assert sum(body["counts"].values()) == BATCH_SIZE
                assert body["counts"]["done"] == done_per_batch(batches)[index]
                assert {item["id"] for item in body["items"]} <= own_ids[tenant.company.pk]
                other = tenants[(index + 1) % 3]
                stranger = tenant.client.get(
                    f"/api/company/projects/{other.project.pk}/processing/"
                )
                assert stranger.status_code == 404

        run_all(check)


class TestABusyProviderNeverFailsAFile:
    def busy(self, context):
        raise AiBusy("RateLimitError")

    def test_the_file_waits_and_the_try_is_not_used(self, plan):
        tenant = Tenant(plan)
        row = tenant.cv(batch=uuid.uuid4())
        register_step("ai_reading", self.busy)
        before = timezone.now()
        processing.run_item(processing.claim_next())
        row.refresh_from_db()
        assert row.status == "waiting"
        assert row.attempts == 0
        assert row.next_attempt_at >= before + timedelta(seconds=29)
        assert processing.claim_next() is None  # it is waiting, not retried at once

    def test_however_often_it_is_told_to_wait_it_never_fails(self, plan, monkeypatch):
        tenant = Tenant(plan)
        row = tenant.cv(batch=uuid.uuid4())
        register_step("ai_reading", self.busy)
        clock = {"now": timezone.now()}
        monkeypatch.setattr(processing, "_now", lambda: clock["now"])
        for _ in range(20):  # far more than `processing.max_attempts`
            processing.run_item(processing.claim_next())
            clock["now"] += timedelta(minutes=5)
        row.refresh_from_db()
        assert row.status == "waiting"
        processing.STEPS.clear()  # the provider calms down
        processing.run_item(processing.claim_next())
        row.refresh_from_db()
        assert row.status == "done"

    def test_other_files_go_on_while_one_waits(self, plan):
        tenant = Tenant(plan)
        slow = tenant.cv(batch=uuid.uuid4())
        quick = tenant.cv(batch=uuid.uuid4())

        def busy_for_the_first(context):
            if context.cv_file.pk == slow.pk:
                raise AiBusy("RateLimitError")

        register_step("ai_reading", busy_for_the_first)
        run_all()
        slow.refresh_from_db(), quick.refresh_from_db()
        assert (slow.status, quick.status) == ("waiting", "done")


class TestParallelUploadsNeverPassALimit:
    """Real threads and real transactions: the company lock is what keeps the counts right."""

    def upload_at_the_same_time(self, tenant, people, files_each):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import connection
        from rest_framework.test import APIClient

        from core.tests.factories import start_session_for
        from cvs.tests.files import make_pdf

        barrier = threading.Barrier(len(people))
        answers = []

        def send(person, number):
            issued = start_session_for(
                user_id=person.pk, role="member", company_id=tenant.company.pk, kind="company"
            )
            client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
            files = [
                SimpleUploadedFile(f"{number}-{n}.pdf", make_pdf(text=f"person {number} file {n}"))
                for n in range(files_each)
            ]
            try:
                barrier.wait()
                answers.append(
                    client.post(
                        f"/api/company/projects/{tenant.project.pk}/cvs/",
                        {"files": files},
                        format="multipart",
                    )
                )
            finally:
                connection.close()

        threads = [
            threading.Thread(target=send, args=(person, number))
            for number, person in enumerate(people)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return answers

    @pytest.mark.django_db(transaction=True)
    def test_the_monthly_limit_is_not_passed_by_uploads_at_the_same_moment(self):
        plan = make_plan(cvs_per_month=4, cvs_per_project=50)
        tenant = Tenant(plan)
        people = [tenant.owner] + [
            make_company_user(tenant.company, role="member") for _ in range(2)
        ]
        self.upload_at_the_same_time(tenant, people, files_each=3)  # nine files asked for four
        assert CvFile.objects.filter(company=tenant.company).count() == 4
        assert usage.waiting_cvs(tenant.company.pk) == 4  # each counted once

    @pytest.mark.django_db(transaction=True)
    def test_a_persons_in_progress_limit_is_not_passed_by_two_uploads_at_the_same_moment(self):
        from cvs.tests.test_cv_upload import set_setting

        plan = make_plan(cvs_per_month=100, cvs_per_project=100)
        tenant = Tenant(plan)
        set_setting("uploads.max_files_in_progress_per_user", 4)
        # the same person on two devices: the limit counts them together
        answers = self.upload_at_the_same_time(tenant, [tenant.owner, tenant.owner], files_each=3)
        assert sorted(answer.status_code for answer in answers) == [200, 409]
        assert CvFile.objects.filter(company=tenant.company).count() == 3
