"""Letting a person download a CV they are allowed to see: the permission check, the file's
response and the log entry every download leaves. Zips of CVs are in `download_packages.py`."""

from django.http import HttpResponse
from django.utils.http import content_disposition_header

import privatefiles
from activity.service import record
from audit.security import watch_cv_downloads
from companies.models import CompanyUser
from companies.role_matrix import roles_allowed
from core.errors import AppError
from core.scoping import get_company_object
from privatefiles import StorageUnavailable, StoredFileMissing

from .models import CvFile


def download_link_for_cv(user, cv_id):
    """A short-lived link to the CV (`{"url", "expires_at"}`) for a signed-in company user.
    The CV must belong to the user's own company and the user's role must allow downloads;
    anything else is "not found" or "not allowed", exactly as for any company record. Archived
    projects can still be downloaded from."""
    cv_file = get_company_object(
        CvFile.objects.all(), user, allowed_roles=roles_allowed("cv.download"), id=cv_id
    )
    return privatefiles.download_link(cv_file.storage_key, cv_file.original_name)


CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
PREVIEW_TYPES = ("pdf",)  # the file types a browser shows inline


def cv_file_response(cv_file, download):
    """The CV's bytes, to show in the page (PDF only) or to save. The caller has already
    checked the person's company and role. The type is fixed by the file type we stored, never
    guessed by the browser."""
    try:
        data = privatefiles.read_file(cv_file.storage_key)
    except StoredFileMissing:
        raise AppError(
            "cv_file_missing", "This CV file is no longer available.", status_code=404
        ) from None
    except StorageUnavailable:
        raise AppError(
            "storage_unavailable", "The file could not be read. Try again soon.", status_code=503
        ) from None
    inline = not download and cv_file.file_type in PREVIEW_TYPES
    response = HttpResponse(
        data, content_type=CONTENT_TYPES.get(cv_file.file_type, "application/octet-stream")
    )
    response["Content-Disposition"] = content_disposition_header(not inline, cv_file.original_name)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def log_download(user, project_id, scope, files):
    """Writes the download to the company's activity log and counts its CVs toward the
    unusual-volume alert. Details hold the kind and the number only, never a name."""
    person = CompanyUser.objects.get(pk=user.user_id, company_id=user.company_id)
    record(
        "download",
        company_id=person.company_id,
        actor=person,
        target_kind="project" if project_id else "",
        target_id=project_id or "",
        details={"scope": scope, "files": files},
    )
    watch_cv_downloads(person, files)
