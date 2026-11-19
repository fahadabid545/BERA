"""Deleting one candidate, by the owner or a member, at any time.

It removes the candidate with everything of theirs (the stored file, the CV record, profile,
contact details, scores, notes and stage history: `candidates.remove_candidate`), and also the
copies that hold their data: any zip of CVs that contains them, and the project's shared reports
that were built with them, whose links then stop working. A CV that is still being processed
cannot be deleted until it is done. The usage history stays. The deletion is written to the
activity log and the audit log by identifiers only, never a name.
"""

from django.db import transaction

from activity.service import record as record_activity
from audit.service import record as record_audit
from companies.models import CompanyUser
from core.errors import AppError

from .candidates import remove_candidate
from .download_packages import remove_packages_with
from .models import CvFile, SharedReport

STILL_PROCESSING = "candidate_processing"


def _reports_with(candidate):
    """The project's shared reports that hold this candidate. A report made before the CVs it
    used were recorded cannot say, so it is treated as holding everyone."""
    cv_id = str(candidate.cv_file_id)
    return [
        report
        for report in SharedReport.objects.filter(
            company_id=candidate.company_id, project_id=candidate.project_id
        )
        if not report.cv_ids or cv_id in report.cv_ids
    ]


def delete_candidate(candidate, user):
    """Deletes the candidate for the signed-in person. Returns nothing; raises if the CV is
    still being processed or the file store cannot delete the file (nothing is deleted then)."""
    if candidate.cv_file.status in CvFile.ACTIVE_STATUSES:
        raise AppError(
            STILL_PROCESSING,
            "This CV is still being processed. Try again in a moment.",
            status_code=409,
        )
    person = CompanyUser.objects.get(pk=user.user_id, company_id=candidate.company_id)
    company_id, project_id = candidate.company_id, candidate.project_id
    cv_id = str(candidate.cv_file_id)
    with transaction.atomic():
        for report in _reports_with(candidate):
            report.delete()
        remove_packages_with(company_id, [cv_id])
        remove_candidate(candidate)
        record_activity(
            "candidate_deleted",
            company_id=company_id,
            actor=person,
            target_kind="project",
            target_id=project_id,
        )
        record_audit(
            "candidate.deleted",
            actor=user,
            company_id=company_id,
            details={"project_id": str(project_id)},
        )
