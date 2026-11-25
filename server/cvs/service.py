"""Uploading CVs to a project: each file is checked on its own, so good files go through while
bad ones get their own clear message.

The server enforces every rule (the screen only mirrors them): type and size, the batch size,
the plan's monthly and per-project CV limits, and the project not being archived. A file is
accepted through `usage.accept_cv` after the limit check, with the company row locked, so two
uploads at once cannot pass a limit together. Accepted files are held (Awaiting confirmation)
until the person confirms the cost estimate (`estimate.py`); Background processing takes them
from there."""

import logging
import uuid
from dataclasses import dataclass

from django.db import transaction

import privatefiles as storage
from companies.models import Company
from core.errors import AppError
from core.validation import safe_file_name
from plans.limits import check_cvs_this_month, split_batch
from platform_settings import maintenance
from platform_settings.service import get_setting
from privatefiles.errors import StorageUnavailable
from projects.deletion import register_project_data
from projects.service import require_editable
from usage import service as usage

from .duplicates import DUPLICATE_FILE, DUPLICATE_FILE_MESSAGE, content_hash, split_identical
from .file_checks import TOO_MANY_FILES, FileCheck, check_cv_file, check_name_and_size
from .models import CvFile

logger = logging.getLogger(__name__)

ACCEPTED = "accepted"
SKIPPED = "skipped"  # already in the project: not an error, and never counted
REJECTED = "rejected"
FAILED = "failed"  # not the file's fault: sending it again may work
STORAGE_FAILED = "storage_failed"
STORAGE_FAILED_MESSAGE = "This file could not be saved. Please try again."
TOO_MANY_IN_PROGRESS = "too_many_in_progress"


@dataclass
class _Candidate:
    index: int
    name: str
    size: int
    check: FileCheck
    cv_id: uuid.UUID | None = None
    key: str = ""
    content_hash: str = ""


def _result(name, status, code="", message="", prompt=None, notice=""):
    return {
        "name": name,
        "status": status,
        "code": code,
        "message": message,
        "prompt": prompt,
        "notice": notice,
    }


def upload_block(company_id):
    """Why a CV sent now would be refused (subscription ended, or the month's allowance used),
    so the screen can say so before anyone tries. None when uploads are open."""
    if maintenance.is_on():
        return {"code": maintenance.CODE, "message": maintenance.message(), "prompt": None}
    check = check_cvs_this_month(company_id)
    if check.allowed:
        return None
    return {"code": check.code, "message": check.message, "prompt": check.prompt}


def files_in_progress(user_id):
    """How many of this person's files are waiting for a decision, waiting or being processed."""
    return CvFile.objects.filter(uploaded_by_id=user_id, status__in=CvFile.ACTIVE_STATUSES).count()


def upload_rules(company_id, user_id=None):
    """What the upload area checks before sending; the server checks again."""
    return {
        "blocked": upload_block(company_id),
        "allowed_types": get_setting("uploads.allowed_file_types"),
        "max_file_size_mb": get_setting("uploads.max_file_size_mb"),
        "max_files_per_batch": get_setting("uploads.max_files_per_batch"),
        "max_files_in_progress": get_setting("uploads.max_files_in_progress_per_user"),
        "files_in_progress": files_in_progress(user_id) if user_id else 0,
        "parallel_uploads": get_setting("uploads.parallel_per_browser"),
    }


def _refuse_if_batch_too_big(project, batch_id, count):
    """A batch is refused as a whole: nothing of it is accepted. The batch is the drop, so files
    already accepted under the same batch id count too (the screen sends each file by itself)."""
    room = get_setting("uploads.max_files_per_batch")
    already = CvFile.objects.filter(company_id=project.company_id, batch_id=batch_id).count()
    if count == 0:
        raise AppError(
            TOO_MANY_FILES,
            "Choose at least one file.",
            fields={"files": "Choose at least one file."},
        )
    if count + already > room:
        raise AppError(
            TOO_MANY_FILES,
            f"Only {room} files can be uploaded at a time. Nothing was added: send fewer files.",
        )


def _refuse_if_too_many_in_progress(uploader, count):
    """One person cannot queue hundreds of files by sending many batches. Refused as a whole."""
    limit = get_setting("uploads.max_files_in_progress_per_user")
    busy = files_in_progress(uploader.pk)
    if busy + count > limit:
        raise AppError(
            TOO_MANY_IN_PROGRESS,
            f"You already have {busy} files waiting or being processed, and at most {limit} are "
            "allowed at a time. Nothing was added: wait for some to finish, then upload again.",
            status_code=409,
        )


def upload_cvs(uploader, project, files, batch_id=None):
    """`files` are (name, size, read) triples in the order sent. Returns one result per file,
    in the same order. `batch_id` groups the files of one drop so it can be cancelled together."""
    maintenance.refuse_if_on()
    require_editable(project)
    batch_id = batch_id or uuid.uuid4()
    _refuse_if_batch_too_big(project, batch_id, len(files))
    _refuse_if_too_many_in_progress(uploader, len(files))  # again under the lock, in `_accept`
    results = [None] * len(files)
    candidates = []
    for index, (name, size, read) in enumerate(files):
        if problem := check_name_and_size(name, size):
            results[index] = _result(name, REJECTED, problem.code, problem.message)
        else:
            data = read()  # one file at a time: its bytes are let go before the next is read
            checked = check_cv_file(name, data)
            if checked.problem:
                results[index] = _result(
                    name, REJECTED, checked.problem.code, checked.problem.message
                )
            elif candidate := _save_file(
                project, _Candidate(index, name, len(data), checked), data
            ):
                candidates.append(candidate)
            else:
                results[index] = _result(name, FAILED, STORAGE_FAILED, STORAGE_FAILED_MESSAGE)
            del data
    if candidates:
        _accept(uploader, project, candidates, results, batch_id)
    return results


def _save_file(project, candidate, data):
    """Saves the file before any limit is checked, so the store's retries never hold the company
    lock, and so a request of many files never holds them all in memory at once. Returns the
    candidate, or None when the store cannot take the file even after trying again."""
    candidate.cv_id = uuid.uuid4()
    candidate.key = storage.key_for_cv(project.company_id, candidate.cv_id)
    candidate.content_hash = content_hash(data)
    try:
        storage.save_file(candidate.key, data)
    except StorageUnavailable:
        return None
    return candidate


def _discard(keys):
    """Removes files that were saved but not kept. If even that fails the file is left for
    clean-up and the key (an identifier, no personal data) is logged."""
    for key in keys:
        try:
            storage.delete_file(key)
        except StorageUnavailable:
            logger.error("An unused file could not be removed: %s", key)


def _accept(uploader, project, candidates, results, batch_id):
    saved = candidates
    kept_keys = []
    try:
        with transaction.atomic():
            # One upload at a time per company, so the limits below cannot be passed together.
            Company.objects.select_for_update().get(pk=project.company_id)
            fresh, repeated = split_identical(project, saved)
            for candidate in repeated:
                results[candidate.index] = _result(
                    candidate.name, SKIPPED, DUPLICATE_FILE, DUPLICATE_FILE_MESSAGE
                )
            in_project = CvFile.objects.filter(project=project).count()
            split = split_batch(project.company_id, fresh, in_project)
            _refuse_if_too_many_in_progress(uploader, len(split.accepted))
            for skipped in split.skipped:
                results[skipped.file.index] = _result(
                    skipped.file.name, REJECTED, skipped.code, skipped.message, skipped.prompt
                )
            for candidate in split.accepted:
                CvFile.objects.create(
                    id=candidate.cv_id,
                    company_id=project.company_id,
                    project=project,
                    original_name=safe_file_name(candidate.name),
                    file_type=candidate.check.file_type,
                    page_count=candidate.check.page_count,
                    size_bytes=candidate.size,
                    storage_key=candidate.key,
                    content_hash=candidate.content_hash,
                    uploaded_by=uploader,
                    batch_id=batch_id,
                    status=CvFile.Status.AWAITING_CONFIRMATION,
                )
                usage.accept_cv(project.company_id, candidate.cv_id, project.pk)
                kept_keys.append(candidate.key)
                results[candidate.index] = _result(
                    candidate.name, ACCEPTED, notice=candidate.check.notice
                )
    except Exception:
        _discard(candidate.key for candidate in saved)  # nothing was recorded
        raise
    _discard(candidate.key for candidate in saved if candidate.key not in kept_keys)


def remove_cv_file(cv_file):
    """Removes one CV: its file from storage, then its record. Deleting a candidate calls this
    for the candidate's CV; the usage ledger keeps its history."""
    storage.delete_file(cv_file.storage_key)
    cv_file.delete()


def _remove_for_project(company_id, project_id):
    for cv_file in CvFile.objects.filter(company_id=company_id, project_id=project_id):
        remove_cv_file(cv_file)


register_project_data("CvFile", _remove_for_project)
