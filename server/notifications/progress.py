"""Emails that follow the work: an upload that finished, and usage nearing or reaching the plan.

Both run after a CV finishes. A problem here is logged (its kind only) and never stops the CV's
own work.
"""

import logging

from cvs.models import CvFile
from emailing.links import build_link
from plans.subscriptions import owner_of
from platform_settings.service import get_setting

from .kinds import BATCH_FINISHED, USAGE_LIMIT_REACHED, USAGE_WARNING
from .service import mark_handled, notify

logger = logging.getLogger(__name__)

USAGE_THINGS = {"cvs": "CV"}
FULL = 100


def _count_text(count, one, many):
    return f"{count} {one if count == 1 else many}"


def upload_finished(company_id, batch_id):
    """Tells the person who uploaded when none of the upload's CVs is still waiting or being
    worked on. An upload that was only cancelled says nothing."""
    if batch_id is None:
        return 0
    files = CvFile.objects.filter(company_id=company_id, batch_id=batch_id)
    if files.filter(status__in=CvFile.ACTIVE_STATUSES).exists():
        return 0
    done = files.filter(status=CvFile.Status.DONE).count()
    failed = files.filter(status=CvFile.Status.FAILED).count()
    first = files.select_related("project", "uploaded_by").order_by("created_at").first()
    if first is None or first.uploaded_by is None or done + failed == 0:
        return 0
    summary = f"{_count_text(done, 'CV was', 'CVs were')} scored"
    if failed:
        summary += f" and {_count_text(failed, 'CV', 'CVs')} could not be read"
    return notify(
        company_id,
        BATCH_FINISHED,
        str(batch_id),
        [first.uploaded_by],
        "batch_finished",
        project=first.project.title,
        summary=summary,
        link=build_link(f"/company/projects/{first.project_id}"),
    )


def _usage_kind(level):
    return USAGE_LIMIT_REACHED if level >= FULL else USAGE_WARNING


def _usage_message(thing, level, used, limit):
    if level >= FULL:
        return (
            f"Your company has reached its monthly {thing} allowance ({used:,} of {limit:,}). "
            "New work waits until the next period or a higher plan."
        )
    return (
        f"Your company has used {level}% of its monthly {thing} allowance ({used:,} of {limit:,})."
    )


def usage_reached(company_id):
    """Emails the owner when a metric first reaches a warning level in a billing period. A jump
    over several levels sends one email, for the highest."""
    from plans.summary import plan_and_usage  # plans imports this app for its own emails

    owner = owner_of(company_id)
    if owner is None:
        return 0
    snapshot = plan_and_usage(company_id)
    period = snapshot["period_start"].isoformat()
    sent = 0
    for metric, thing in USAGE_THINGS.items():
        figures = snapshot[metric]
        level = figures["warning"]
        if level is None:
            continue
        for lower in (p for p in get_setting("usage.warning_percents") if p < level):
            mark_handled(company_id, _usage_kind(lower), f"{metric}:{period}:{lower}")
        sent += notify(
            company_id,
            _usage_kind(level),
            f"{metric}:{period}:{level}",
            [owner],
            "usage_notice",
            title="Your usage is high" if level < FULL else "Your usage limit was reached",
            message=_usage_message(thing, level, figures["used"], figures["limit"]),
            link=build_link("/company/billing"),
        )
    return sent


def after_cv_finished(cv_file):
    """Called when a CV reaches done, failed or cancelled."""
    try:
        upload_finished(cv_file.company_id, cv_file.batch_id)
    except Exception as error:
        logger.error("An upload notice could not be sent (%s).", type(error).__name__)


def after_cv_counted(company_id):
    """Called when a CV was counted against the month."""
    try:
        usage_reached(company_id)
    except Exception as error:
        logger.error("A usage notice could not be sent (%s).", type(error).__name__)
