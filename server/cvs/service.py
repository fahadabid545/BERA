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
from core.validation import safe_file_name
from plans.limits import split_batch
from platform_settings.service import get_setting
from privatefiles.errors import StorageUnavailable
from projects.deletion import register_project_data
from projects.service import require_editable
from usage import service as usage

from .duplicates import DUPLICATE_FILE, DUPLICATE_FILE_MESSAGE, split_identical
from .file_checks import TOO_MANY_FILES, FileCheck, check_cv_file, check_name_and_size
from .models import CvFile

logger = logging.getLogger(__name__)

ACCEPTED = "accepted"
SKIPPED = "skipped"  # already in the project: not an error, and never counted
REJECTED = "rejected"
FAILED = "failed"  # not the file's fault: sending it again may work
STORAGE_FAILED = "storage_failed"
STORAGE_FAILED_MESSAGE = "This file could not be saved. Please try again."


@dataclass
class _Candidate:
    index: int
    name: str
    data: bytes
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


def upload_rules():
    """What the upload area checks before sending; the server checks again."""
    return {
        "allowed_types": get_setting("uploads.allowed_file_types"),
        "max_file_size_mb": get_setting("uploads.max_file_size_mb"),
        "max_files_per_batch": get_setting("uploads.max_files_per_batch"),
    }


def upload_cvs(uploader, project, files, batch_id=None):
    """`files` are (name, size, read) triples in the order sent. Returns one result per file,
    in the same order. `batch_id` groups the files of one drop so it can be cancelled together."""
    require_editable(project)
    batch_id = batch_id or uuid.uuid4()
    results = [None] * len(files)
    candidates = []
    room = get_setting("uploads.max_files_per_batch")
    for index, (name, size, read) in enumerate(files):
        if index >= room:
            results[index] = _result(
                name, REJECTED, TOO_MANY_FILES, f"Only {room} files can be added at a time."
            )
        elif problem := check_name_and_size(name, size):
            results[index] = _result(name, REJECTED, problem.code, problem.message)
        else:
            data = read()
            checked = check_cv_file(name, data)
            if checked.problem:
                results[index] = _result(
                    name, REJECTED, checked.problem.code, checked.problem.message
                )
            else:
                candidates.append(_Candidate(index, name, data, checked))
    if candidates:
        _accept(uploader, project, candidates, results, batch_id)
    return results


def _store(candidates, results, project):
    """Saves each file before any limit is checked, so the store's retries never hold the
    company lock. A file the store cannot take (even after trying again) is a failed file;
    the others go on. Returns the candidates that were saved."""
    saved = []
    for candidate in candidates:
        candidate.cv_id = uuid.uuid4()
        candidate.key = storage.key_for_cv(project.company_id, candidate.cv_id)
        try:
            storage.save_file(candidate.key, candidate.data)
        except StorageUnavailable:
            results[candidate.index] = _result(
                candidate.name, FAILED, STORAGE_FAILED, STORAGE_FAILED_MESSAGE
            )
        else:
            saved.append(candidate)
    return saved


def _discard(keys):
    """Removes files that were saved but not kept. If even that fails the file is left for
    clean-up and the key (an identifier, no personal data) is logged."""
    for key in keys:
        try:
            storage.delete_file(key)
        except StorageUnavailable:
            logger.error("An unused file could not be removed: %s", key)


def _accept(uploader, project, candidates, results, batch_id):
    saved = _store(candidates, results, project)
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
                    size_bytes=len(candidate.data),
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
