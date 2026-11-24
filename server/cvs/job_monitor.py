"""The jobs monitor: what an admin sees of the background work, and how they fix it.

A job is one CV going through processing (`processing.py`). It is in one of four states:

- waiting: in line for a turn (a retry that is due later, and work held while AI is paused, too);
- running: a worker has it and has had it for less than `processing.stuck_minutes`;
- stuck: a worker has had it for longer than that. The once-a-minute sweep puts such a job back in
  line by itself, so one shown here is one that sweep has not reached yet or cannot;
- failed: it gave up, and `failure_reason` says why in words for the person.

Only a failed or stuck job can be retried and only a waiting or stuck one can be cancelled (work
that is running is let finish, as when a company cancels an upload). Both go through the same
steps real processing uses: a retry reopens the CV's usage entry, which is a no-op for one already
open, and the processing steps never read or score twice, so a retry can repeat neither results nor
usage. A cancel gives the allowance back. Both are audited. Nothing here shows a file name or any
CV content, which is candidate data.
"""

from uuid import UUID

from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404

from ai import control
from audit.service import record
from companies.models import Company
from core.errors import AppError
from notifications.progress import after_cv_finished
from platform_settings.service import get_setting
from usage import service as usage

from . import processing
from .models import CvFile

WAITING, RUNNING, FAILED, STUCK = "waiting", "running", "failed", "stuck"
STATES = (WAITING, RUNNING, FAILED, STUCK)
RETRYABLE = (FAILED, STUCK)
CANCELLABLE = (WAITING, STUCK)
WORKING = (CvFile.Status.READING, CvFile.Status.SCORING)

NOT_RETRYABLE_CODE, NOT_CANCELLABLE_CODE = "job_not_retryable", "job_not_cancellable"
NOT_RETRYABLE_MESSAGE = "Only a failed or stuck job can be retried."
NOT_CANCELLABLE_MESSAGE = "Only a waiting or stuck job can be cancelled."
REASONS = {
    WAITING: "Waiting for its turn.",
    "retry": "Waiting to try again.",
    RUNNING: "Being processed.",
    STUCK: processing.TOO_LONG_REASON,
}


def _filter_for(state, cutoff):
    """The rows in `state`, as a query filter."""
    if state == WAITING:
        return Q(status=CvFile.Status.WAITING)
    if state == FAILED:
        return Q(status=CvFile.Status.FAILED)
    since_cutoff = Q(started_at__lt=cutoff)
    return Q(status__in=WORKING) & (since_cutoff if state == STUCK else ~since_cutoff)


def state_of(item, cutoff):
    """The state a job is in, or None for one that is not background work now (done, cancelled
    or waiting for the person to confirm its estimate)."""
    if item.status == CvFile.Status.FAILED:
        return FAILED
    if item.status == CvFile.Status.WAITING:
        return WAITING
    if item.status in WORKING:
        return STUCK if item.started_at and item.started_at < cutoff else RUNNING
    return None


def _reason(item, state):
    if state == FAILED:
        return item.failure_reason
    if state == WAITING:
        if control.is_paused():
            return control.PAUSED_MESSAGE
        return REASONS["retry" if item.attempts else WAITING]
    return REASONS[state]


def _describe(item, state):
    return {
        "id": str(item.pk),
        "company_id": str(item.company_id),
        "company": item.company.name,
        "project": item.project.title,
        "state": state,
        "tries": item.attempts,
        "reason": _reason(item, state),
        "since": (item.started_at or item.finished_at or item.next_attempt_at).isoformat(),
        "can_retry": state in RETRYABLE,
        "can_cancel": state in CANCELLABLE,
    }


def _per_company(cutoff):
    counts = {
        state: Count("pk", filter=_filter_for(state, cutoff), distinct=True) for state in STATES
    }
    rows = CvFile.objects.values("company_id").annotate(**counts).order_by()
    found = {row["company_id"]: row for row in rows if any(row[state] for state in STATES)}
    names = dict(Company.objects.filter(pk__in=found).values_list("pk", "name"))
    return sorted(
        (
            {"id": str(company_id), "name": names[company_id], **{s: row[s] for s in STATES}}
            for company_id, row in found.items()
        ),
        key=lambda entry: (entry["name"].casefold(), entry["id"]),
    )


def list_jobs(*, state=None, company_id=None, now=None):
    """The counts per company and the jobs, grouped by company name, for an optional state and
    company. At most `admin_jobs.list_limit` jobs are listed, with the real total."""
    now = now or processing._now()
    cutoff = processing.stuck_cutoff(now)
    companies = _per_company(cutoff)
    states = (state,) if state else STATES
    wanted = Q()
    for each in states:
        wanted |= _filter_for(each, cutoff)
    jobs = CvFile.objects.filter(wanted).select_related("company", "project")
    if company_id:
        jobs = jobs.filter(company_id=company_id)
    total = jobs.count()
    ordered = jobs.order_by("company__name", "company_id", "created_at")
    items = []
    for item in ordered[: get_setting("admin_jobs.list_limit")]:
        items.append(_describe(item, state_of(item, cutoff)))
    return {
        "totals": {s: sum(entry[s] for entry in companies) for s in STATES},
        "companies": companies,
        "total": total,
        "items": items,
    }


def failed_count():
    return CvFile.objects.filter(status=CvFile.Status.FAILED).count()


def _find(job_id):
    try:
        return CvFile.objects.select_related("company", "project").get(pk=UUID(str(job_id)))
    except (ValueError, CvFile.DoesNotExist) as error:
        raise Http404 from error


def _requeue_stuck(job_id, now):
    """A stuck job goes back in line with fresh tries. Its old claim is dropped, so the worker
    that held it can no longer change it. Its usage entry is untouched (still waiting)."""
    with transaction.atomic():
        item = CvFile.objects.select_for_update().get(pk=job_id)
        if state_of(item, processing.stuck_cutoff(now)) != STUCK:
            raise AppError(NOT_RETRYABLE_CODE, NOT_RETRYABLE_MESSAGE, status_code=409)
        item.status, item.attempts = CvFile.Status.WAITING, 0
        item.started_at, item.claim_token, item.next_attempt_at = None, None, now
        item.save(
            update_fields=["status", "attempts", "started_at", "claim_token", "next_attempt_at"]
        )
    processing.kick(1)


def retry_job(admin, job_id):
    """Puts a failed or stuck job back in line. Retrying a failed job counts against its
    company's month again, so its limit is checked (409 when there is no room)."""
    item = _find(job_id)
    now = processing._now()
    state = state_of(item, processing.stuck_cutoff(now))
    if state == FAILED:
        processing.retry_failed(item)
    elif state == STUCK:
        _requeue_stuck(item.pk, now)
    else:
        raise AppError(NOT_RETRYABLE_CODE, NOT_RETRYABLE_MESSAGE, status_code=409)
    record(
        "admin.job_retried",
        actor=admin,
        company_id=item.company_id,
        details={"job_id": str(item.pk), "was": state},
    )


def cancel_job(admin, job_id):
    """Cancels a waiting or stuck job. It is never counted, and its allowance goes back."""
    now = processing._now()
    found = _find(job_id)
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=found.company_id)
        item = CvFile.objects.select_for_update().get(pk=found.pk)
        state = state_of(item, processing.stuck_cutoff(now))
        if state not in CANCELLABLE:
            raise AppError(NOT_CANCELLABLE_CODE, NOT_CANCELLABLE_MESSAGE, status_code=409)
        item.status, item.finished_at, item.claim_token = CvFile.Status.CANCELLED, now, None
        item.save(update_fields=["status", "finished_at", "claim_token"])
        usage.mark_failed(item.company_id, item.pk)
        record(
            "admin.job_cancelled",
            actor=admin,
            company_id=item.company_id,
            details={"job_id": str(item.pk), "was": state},
        )
    after_cv_finished(item)  # cancelling can be what finishes an upload
