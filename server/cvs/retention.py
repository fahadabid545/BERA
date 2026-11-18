"""How long candidate data is kept.

A company keeps its CVs, profiles, contact details, scores, notes and stored files for its
retention period counted from the upload (`activity.service.retention_days`: the owner's choice
or the platform default). A daily job deletes what is older, and a week before (the platform's
`retention.warning_days`) emails the owners once, with a count and a date and nothing about any
candidate. A shared report holds a copy of candidate data, so it goes when its oldest CV does,
and its link then answers like any link that does not exist. Deletions are logged with counts
only. The usage history stays. Backups are not touched here; they age out under their own policy
(see Daily backups).
"""

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from activity.service import purge_expired_entries, record, retention_cutoff, retention_days
from companies.models import Company, CompanyUser
from core.jobs import logged_job
from emailing.links import build_link
from emailing.rendering import format_moment
from emailing.service import send_email
from platform_settings.service import get_setting
from privatefiles.errors import StorageUnavailable

from .download_packages import remove_packages_with
from .models import CvFile, SharedReport
from .service import remove_cv_file

logger = logging.getLogger(__name__)


def _finished_cvs(company_id):
    """The company's CVs that are not being processed: a CV still on its way is never deleted
    under the worker's hands."""
    return CvFile.objects.filter(company_id=company_id).exclude(status__in=CvFile.ACTIVE_STATUSES)


def _reports_from_before(company_id, cutoff):
    return SharedReport.objects.filter(company_id=company_id).filter(
        Q(data_from__lt=cutoff) | Q(data_from__isnull=True, created_at__lt=cutoff)
    )


def preview(company_id, days):
    """What a retention period of `days` would delete now, so the owner sees it before choosing
    a shorter one."""
    cutoff = timezone.now() - timedelta(days=days)
    due = _finished_cvs(company_id).filter(created_at__lt=cutoff)
    return {
        "cvs": due.count(),
        "projects": due.values("project_id").distinct().count(),
        "shared_links": _reports_from_before(company_id, cutoff).count(),
    }


def purge_company(company_id):
    """Deletes what is past the company's retention period. A file the store cannot delete is
    left whole (nothing half-deleted) and tried again at the next run. Returns the counts."""
    cutoff = retention_cutoff(company_id)
    removed_ids = []
    for cv_file in _finished_cvs(company_id).filter(created_at__lt=cutoff).order_by("created_at"):
        cv_id = cv_file.pk
        try:
            remove_cv_file(cv_file)
        except StorageUnavailable:
            logger.warning("A CV past its retention period could not be deleted yet.")
            continue
        removed_ids.append(str(cv_id))
    remove_packages_with(company_id, removed_ids)
    links, _ = _reports_from_before(company_id, cutoff).delete()
    if removed_ids or links:
        record(
            "data_expired",
            company_id=company_id,
            actor=None,
            details={"files": len(removed_ids), "shared_links": links},
        )
    return {"cvs": len(removed_ids), "shared_links": links}


def _files_text(count):
    return f"{count} CV" if count == 1 else f"{count} CVs"


def warn_company(company_id, now=None):
    """Emails the owners once about CVs that will be deleted within the warning time. Returns
    how many CVs the warning covered."""
    now = now or timezone.now()
    cutoff = retention_cutoff(company_id)  # CVs uploaded before this are already due
    soon = cutoff + timedelta(days=get_setting("retention.warning_days"))
    coming = _finished_cvs(company_id).filter(
        created_at__gte=cutoff, created_at__lt=soon, expiry_warned_at__isnull=True
    )
    first = coming.order_by("created_at").values_list("created_at", flat=True).first()
    if first is None:
        return 0
    owners = list(
        CompanyUser.objects.filter(
            company_id=company_id, role=CompanyUser.Role.OWNER, status=CompanyUser.Status.ACTIVE
        )
    )
    deletion_time = first + timedelta(days=retention_days(company_id))
    count = coming.count()
    for owner in owners:
        send_email(
            "retention_warning",
            owner.email,
            name=owner.name,
            files=_files_text(count),
            when=format_moment(deletion_time),
            link=build_link("/company/advanced/retention"),
        )
    coming.update(expiry_warned_at=now)
    return count


def forget_warnings(company_id):
    """After the period changes, the warnings start over: a longer one makes earlier warnings
    untrue, a shorter one needs its own."""
    CvFile.objects.filter(company_id=company_id).update(expiry_warned_at=None)


@logged_job
def run_retention():
    """The daily job: deletes what is past each company's retention period, warns about what is
    close, and clears old activity entries. Returns how many CVs were deleted."""
    deleted = 0
    for company_id in Company.objects.values_list("pk", flat=True):
        deleted += purge_company(company_id)["cvs"]
        warn_company(company_id)
    purge_expired_entries()
    return deleted
