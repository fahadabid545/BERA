"""Downloading CVs as one zip: one CV's package, chosen CVs, or every CV of a project.

A package belongs to the person who asked for it and to their company; nobody else can see or
download it, and the role is checked on every request, so a person whose access was removed
loses the package too. Up to `downloads.background_over_files` files the zip is made while the
person waits; more is made by a background job and the person gets an email that says only that
it is ready and links to the app, where they sign in and download it as usual. The zip is kept
for `sharing.download_package_link_hours`, then its file is removed.
"""

import io
import logging
import uuid
import zipfile
from datetime import timedelta
from pathlib import PurePosixPath

from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django_q.tasks import async_task

import privatefiles
from companies.models import CompanyUser
from core.errors import AppError, form_error
from core.jobs import logged_job
from emailing.links import build_link
from emailing.rendering import duration_text
from emailing.service import send_email
from platform_settings.service import get_setting
from projects.deletion import register_project_data

from .downloads import log_download
from .models import CvFile, DownloadPackage

logger = logging.getLogger(__name__)

BUILD_JOB = "cvs.download_packages.build_package"
ZIP_NAME = "cvs.zip"


def _cv_ids(project, raw_candidate_ids):
    """The ids of the CVs to download: every CV of the project (`raw_candidate_ids` is None) or
    the CVs of the chosen candidates, who must all be this project's. Cancelled CVs are left
    out: they were never read."""
    own = CvFile.objects.filter(company_id=project.company_id, project=project).exclude(
        status=CvFile.Status.CANCELLED
    )
    if raw_candidate_ids is None:
        ids = list(own.order_by("created_at", "id").values_list("id", flat=True))
    else:
        if not isinstance(raw_candidate_ids, list) or not raw_candidate_ids:
            raise form_error({"candidate_ids": "Choose at least one candidate."})
        try:
            chosen = {uuid.UUID(str(item)) for item in raw_candidate_ids}
        except ValueError:
            raise form_error({"candidate_ids": "Choose candidates from the list."}) from None
        ids = list(
            own.filter(candidate__pk__in=chosen)
            .order_by("created_at", "id")
            .values_list("id", flat=True)
        )
        if len(ids) != len(chosen):
            raise form_error({"candidate_ids": "Choose candidates from the list."})
    if not ids:
        raise AppError("nothing_to_download", "There are no CVs to download.", status_code=400)
    return ids


def request_package(project, user, raw_candidate_ids=None):
    """Starts a package of the project's CVs for the signed-in person and returns it. A small
    one is ready when this returns; a larger one is made in the background."""
    ids = _cv_ids(project, raw_candidate_ids)
    package = DownloadPackage.objects.create(
        company_id=project.company_id,
        project=project,
        requested_by=CompanyUser.objects.get(pk=user.user_id, company_id=project.company_id),
        cv_ids=[str(item) for item in ids],
        file_count=len(ids),
    )
    if len(ids) > get_setting("downloads.background_over_files"):
        async_task(BUILD_JOB, str(package.pk))
    else:
        _build(package, notify=False)
    package.refresh_from_db()
    return package


def _zip_names(cv_files):
    """File names for inside the zip: the original names, made safe, with a number added to
    any name used twice."""
    used = set()
    names = []
    for cv_file in cv_files:
        path = PurePosixPath(cv_file.original_name.replace("\\", "/"))
        name = path.name or f"cv-{cv_file.pk}"
        candidate, number = name, 1
        while candidate.lower() in used:
            number += 1
            candidate = f"{path.stem or 'cv'} ({number}){path.suffix}"
        used.add(candidate.lower())
        names.append(candidate)
    return names


def _zip_of(cv_files):
    buffer = io.BytesIO()
    # The CVs are PDF and Word files, already compressed, so storing them is as small and faster.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for cv_file, name in zip(cv_files, _zip_names(cv_files), strict=True):
            archive.writestr(name, privatefiles.read_file(cv_file.storage_key))
    return buffer.getvalue()


def _fail(package, reason):
    package.status = DownloadPackage.Status.FAILED
    package.save(update_fields=["status"])
    logger.warning("A download package was not made (%s).", reason)


def _build(package, *, notify):
    ids = package.cv_ids
    cv_files = list(
        CvFile.objects.filter(company_id=package.company_id, project=package.project, id__in=ids)
        .exclude(status=CvFile.Status.CANCELLED)
        .order_by("created_at", "id")
    )
    if len(cv_files) != len(ids):  # some were removed since the package was asked for
        _fail(package, "cv_removed")
        return
    try:
        data = _zip_of(cv_files)
        key = privatefiles.key_for_package(package.company_id, package.pk)
        privatefiles.save_file(key, data)
    except (privatefiles.StoredFileMissing, privatefiles.StorageUnavailable) as error:
        _fail(package, type(error).__name__)
        return
    now = timezone.now()
    hours = get_setting("sharing.download_package_link_hours")
    package.status = DownloadPackage.Status.READY
    package.storage_key = key
    package.size_bytes = len(data)
    package.ready_at = now
    package.expires_at = now + timedelta(hours=hours)
    package.save()
    if notify:
        _tell_it_is_ready(package, hours)


def _tell_it_is_ready(package, hours):
    """The email holds no CV, name or file name, and no direct file link: only a link to the
    page in the app where the person signs in and downloads."""
    person = package.requested_by
    if person is None:
        return
    send_email(
        "download_ready",
        person.email,
        name=person.name,
        link=build_link(f"/company/downloads/{package.pk}"),
        expires_in=duration_text(hours, "hour"),
    )


@logged_job
def build_package(package_id):
    """Background job: makes a large package and emails the person who asked for it."""
    package = (
        DownloadPackage.objects.select_related("project", "requested_by")
        .filter(pk=package_id, status=DownloadPackage.Status.PREPARING)
        .first()
    )
    if package is not None:  # a repeated job finds it done and does nothing
        _build(package, notify=True)


def status_of(package, now=None):
    """The status to show: a ready package past its time is expired, even before its file is
    removed."""
    if package.status == DownloadPackage.Status.READY and package.expires_at <= (
        now or timezone.now()
    ):
        return DownloadPackage.Status.EXPIRED
    return package.status


def describe(package):
    return {
        "id": str(package.pk),
        "project_id": str(package.project_id),
        "status": status_of(package),
        "files": package.file_count,
        "size_bytes": package.size_bytes,
        "created_at": package.created_at.isoformat(),
        "expires_at": package.expires_at.isoformat() if package.expires_at else None,
    }


def require_owner(package, user):
    """Only the person who asked for the package may see or download it; anyone else in the
    company gets "not found"."""
    if package.requested_by_id != user.user_id:
        raise Http404


NOT_AVAILABLE = {
    DownloadPackage.Status.PREPARING: ("package_not_ready", "This download is not ready yet."),
    DownloadPackage.Status.FAILED: (
        "package_failed",
        "This download could not be made. Ask for it again.",
    ),
    DownloadPackage.Status.EXPIRED: ("package_expired", "This download has expired."),
}


def package_response(user, package):
    """The zip, for the person it belongs to. Counted and logged as a download of its CVs."""
    status = status_of(package)
    if status != DownloadPackage.Status.READY:
        code, message = NOT_AVAILABLE[status]
        raise AppError(code, message, status_code=410 if status == "expired" else 409)
    try:
        data = privatefiles.read_file(package.storage_key)
    except privatefiles.StoredFileMissing:
        raise AppError("package_expired", NOT_AVAILABLE["expired"][1], status_code=410) from None
    except privatefiles.StorageUnavailable:
        raise AppError(
            "storage_unavailable", "The file could not be read. Try again soon.", status_code=503
        ) from None
    log_download(user, package.project_id, "package", package.file_count)
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Disposition"] = content_disposition_header(True, ZIP_NAME)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@logged_job
def remove_expired_packages():
    """Removes the files of packages past their time and marks them expired; for a periodic
    job. Returns how many were removed."""
    due = DownloadPackage.objects.filter(
        status=DownloadPackage.Status.READY, expires_at__lte=timezone.now()
    )
    removed = 0
    for package in due:
        privatefiles.delete_file(package.storage_key)
        package.status = DownloadPackage.Status.EXPIRED
        package.storage_key = ""
        package.save(update_fields=["status", "storage_key"])
        removed += 1
    return removed


def remove_packages_with(company_id, cv_ids):
    """Removes the company's packages (file and record) that hold any of these CVs, so a CV
    deleted by the retention period is not left inside a zip."""
    gone = set(cv_ids)
    if not gone:
        return
    for package in DownloadPackage.objects.filter(company_id=company_id):
        if gone.intersection(package.cv_ids):
            if package.storage_key:
                privatefiles.delete_file(package.storage_key)
            package.delete()


def _remove_for_project(company_id, project_id):
    for package in DownloadPackage.objects.filter(company_id=company_id, project_id=project_id):
        if package.storage_key:
            privatefiles.delete_file(package.storage_key)
    DownloadPackage.objects.filter(company_id=company_id, project_id=project_id).delete()


register_project_data("DownloadPackage", _remove_for_project)
