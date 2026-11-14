"""Processing uploaded CVs in the background, so people can leave the page.

**The queue is the database.** A CV is a row (`CvFile`) with a status: waiting, reading, scoring,
done, failed or cancelled. Nothing is lost when the server restarts: the rows are still there, a
once-a-minute sweep (`sweep`) picks up anything that was waiting, and a CV stuck in a try for more
than `processing.stuck_minutes` (5) is tried again.

**Nothing runs twice.** A worker *claims* a CV by giving it a fresh `claim_token` in one atomic
step (rows already claimed by another worker are skipped). Only the holder of the token can change
the CV afterwards, so a worker that was replaced after a timeout can never overwrite the new one.

**Fair between companies.** Each claim goes to the company that has waited longest for a turn
(`ProcessingTurn`), then to its oldest waiting CV, so a company with a thousand CVs and a company
with two take turns. Each task does one CV and then asks for the next.

**Steps plug into named slots** (`SLOTS`, in order). A slot with no step is skipped. Each ticket
that builds a step registers it with `register_step(slot, function)` and adds its own test; the
test of the exact list of registered slots (`test_processing.py`) must be updated with it. A step
gets a `StepContext` (the CV, its company and project, and `state`, a dict that carries results
to the later steps of the same try) and either returns, raises `PermanentFailure("words for the
person")` (the file itself is the problem: no more tries), or raises anything else (a hiccup:
tried again after a wait, up to `processing.max_attempts`, then failed).

A failed CV is not counted (`usage.mark_failed`); retrying it counts it again."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, OuterRef, Subquery
from django.utils import timezone
from django_q.tasks import async_task

from companies.models import Company
from core.errors import AppError
from core.jobs import logged_job
from plans.limits import check_cvs_this_month
from platform_settings.service import get_setting
from projects.deletion import register_work_stopper
from projects.service import require_editable
from usage import service as usage

from .models import CvFile, ProcessingTurn

logger = logging.getLogger(__name__)

SLOTS = (
    "text_reading",
    "ai_reading",
    "fairness_guard",
    "candidate_record",
    "requirement_evaluation",
    "scoring",
)
READING, SCORING = CvFile.Status.READING, CvFile.Status.SCORING
SLOT_STATUS = {
    "text_reading": READING,
    "ai_reading": READING,
    "fairness_guard": READING,
    "candidate_record": READING,
    "requirement_evaluation": SCORING,
    "scoring": SCORING,
}
STEPS = {}

TICK_JOB = "cvs.processing.tick"
GAVE_UP_REASON = "We could not process this file after several tries. You can retry it."
TOO_LONG_REASON = "Processing this file took too long. You can retry it."
NOT_FAILED_CODE = "not_failed"


class PermanentFailure(Exception):
    """A step says the file itself cannot be processed; the message is shown to the person."""


@dataclass
class StepContext:
    cv_file: CvFile
    company_id: int
    project_id: uuid.UUID
    state: dict = field(default_factory=dict)


def register_step(slot, step):
    if slot not in SLOTS:
        raise KeyError(slot)  # a mistake in the code, so it fails loudly
    STEPS[slot] = step


def kick(count=1):
    """Asks the workers to look for work. If the queue itself is down the CVs still wait in the
    database and the sweep finds them within a minute, so the upload is not failed for it."""
    for _ in range(count):
        try:
            async_task(TICK_JOB)
        except Exception:
            logger.exception("Could not ask the workers to start; the sweep will.")
            return


def _now():
    return timezone.now()


def claim_next(now=None):
    """The next CV to work on, fairly: the company that waited longest for a turn, then its
    oldest CV. Returns the claimed CV (now reading, with a new `claim_token`) or None."""
    now = now or _now()
    turn = ProcessingTurn.objects.filter(company_id=OuterRef("company_id")).values(
        "last_served_at"
    )[:1]
    with transaction.atomic():
        item = (
            CvFile.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(status=CvFile.Status.WAITING, next_attempt_at__lte=now)
            .annotate(last_served=Subquery(turn))
            .order_by(F("last_served").asc(nulls_first=True), "next_attempt_at", "created_at")
            .first()
        )
        if item is None:
            return None
        item.status = READING
        item.attempts += 1
        item.started_at = now
        item.claim_token = uuid.uuid4()
        item.save(update_fields=["status", "attempts", "started_at", "claim_token"])
        ProcessingTurn.objects.update_or_create(
            company_id=item.company_id, defaults={"last_served_at": now}
        )
    return item


def _holds(item):
    """Updates the CV only while this worker still holds it. Returns the matching rows."""
    return CvFile.objects.filter(pk=item.pk, claim_token=item.claim_token)


def _wait_before_try(attempt):
    waits = get_setting("processing.retry_waits_seconds")
    return timedelta(seconds=waits[min(attempt, len(waits)) - 1])


def _give_up(item, reason, now):
    updated = _holds(item).update(
        status=CvFile.Status.FAILED,
        failure_reason=reason,
        finished_at=now,
        claim_token=None,
    )
    if updated:
        usage.mark_failed(item.company_id, item.pk)  # a failed CV is never counted
    return updated


def _try_again_or_give_up(item, reason, now):
    """After a failed try: wait and try again, or fail for good when the tries are used up."""
    if item.attempts >= get_setting("processing.max_attempts"):
        return _give_up(item, reason, now)
    return _holds(item).update(
        status=CvFile.Status.WAITING,
        next_attempt_at=now + _wait_before_try(item.attempts),
        started_at=None,
        claim_token=None,
    )


def run_item(item):
    """Runs the steps for a claimed CV, in slot order. A slot with no step is skipped."""
    context = StepContext(item, item.company_id, item.project_id)
    for slot in SLOTS:
        step = STEPS.get(slot)
        if step is None:
            continue
        if not _holds(item).update(status=SLOT_STATUS[slot]):
            return  # another worker has taken over (or the project was deleted): leave it
        try:
            step(context)
        except PermanentFailure as failure:
            _give_up(item, str(failure), _now())
            return
        except Exception as error:
            # The kind of error is logged (never its message or the CV): it can hold CV text.
            logger.error("Processing step %s failed with %s.", slot, type(error).__name__)
            _try_again_or_give_up(item, GAVE_UP_REASON, _now())
            return
    _holds(item).update(status=CvFile.Status.DONE, finished_at=_now(), claim_token=None)


@logged_job
def tick():
    """One task for the workers: do the next CV, then ask for another turn if more are due."""
    item = claim_next()
    if item is None:
        return
    run_item(item)
    if CvFile.objects.filter(status=CvFile.Status.WAITING, next_attempt_at__lte=_now()).exists():
        kick(1)


@logged_job
def sweep():
    """Once a minute. Puts a CV that has been stuck in one try too long back in line (or fails
    it when its tries are used up), and wakes the workers if CVs are waiting, which also covers
    work whose task was lost in a restart."""
    now = _now()
    cutoff = now - timedelta(minutes=get_setting("processing.stuck_minutes"))
    with transaction.atomic():
        stuck = CvFile.objects.select_for_update(skip_locked=True, of=("self",)).filter(
            status__in=(READING, SCORING), started_at__lt=cutoff
        )
        for item in stuck:
            _try_again_or_give_up(item, TOO_LONG_REASON, now)
    due = CvFile.objects.filter(status=CvFile.Status.WAITING, next_attempt_at__lte=now).count()
    kick(min(due, settings.Q_CLUSTER["workers"]))


def cancel_unstarted(project, batch_id=None):
    """Skips the CVs of a project (or of one upload) that have not started. Each gives its
    allowance back. Work already running finishes. Returns how many were skipped."""
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=project.company_id)
        waiting = CvFile.objects.filter(project=project, status=CvFile.Status.WAITING)
        if batch_id is not None:
            waiting = waiting.filter(batch_id=batch_id)
        skipped = list(waiting.select_for_update())
        for item in skipped:
            item.status, item.finished_at = CvFile.Status.CANCELLED, _now()
            item.save(update_fields=["status", "finished_at"])
            usage.mark_failed(item.company_id, item.pk)
    return len(skipped)


def retry_failed(cv_file):
    """Puts a failed CV back in line. It counts against the month again, so the limit is
    checked first (409 with the Upgrade prompt when there is no room)."""
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=cv_file.company_id)
        item = CvFile.objects.select_for_update().get(pk=cv_file.pk)
        require_editable(item.project)
        if item.status != CvFile.Status.FAILED:
            raise AppError(NOT_FAILED_CODE, "Only a failed file can be retried.", status_code=409)
        check_cvs_this_month(item.company_id).raise_if_blocked()
        usage.reopen_cv(item.company_id, item.pk)
        item.status, item.attempts, item.failure_reason = CvFile.Status.WAITING, 0, ""
        item.next_attempt_at, item.finished_at = _now(), None
        item.save(
            update_fields=["status", "attempts", "failure_reason", "next_attempt_at", "finished_at"]
        )
    kick(1)
    return item


def project_processing(project):
    """What the project page shows: a count per status and the CVs, newest first."""
    counts = dict(
        CvFile.objects.filter(project=project)
        .values_list("status")
        .annotate(total=Count("id"))
        .order_by()
    )
    items = CvFile.objects.filter(project=project).order_by("-created_at")[
        : get_setting("processing.list_limit")
    ]
    return {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "counts": {status: counts.get(status, 0) for status in CvFile.Status.values},
        "items": [
            {
                "id": str(item.id),
                "name": item.original_name,
                "status": item.status,
                "reason": item.failure_reason,
                "can_retry": item.status == CvFile.Status.FAILED,
            }
            for item in items
        ],
    }


def _stop_for_project(company_id, project_id):
    """Deleting a project: work not yet finished is stopped first. Taking the claim away means
    a worker still busy with a CV of this project can no longer change anything."""
    CvFile.objects.filter(
        company_id=company_id, project_id=project_id, status__in=CvFile.ACTIVE_STATUSES
    ).update(status=CvFile.Status.CANCELLED, claim_token=None, finished_at=_now())


register_work_stopper("CvProcessing", _stop_for_project)
