"""Uploading CVs to a project: each file is checked on its own, so good files go through while
bad ones get their own clear message.

The server enforces every rule (the screen only mirrors them): type and size, the batch size,
the plan's monthly and per-project CV limits, and the project not being archived. A file is
accepted through `usage.accept_cv` after the limit check, with the company row locked, so two
uploads at once cannot pass a limit together. Accepted files stay Waiting; Background
processing takes them from there."""

import uuid
from dataclasses import dataclass

from django.db import transaction

from companies.models import Company
from core.validation import safe_file_name
from plans.limits import split_batch
from platform_settings.service import get_setting
from projects.deletion import register_project_data
from projects.service import require_editable
from usage import service as usage

from . import storage
from .file_checks import TOO_MANY_FILES, FileCheck, check_cv_file, check_name_and_size
from .models import CvFile

ACCEPTED = "accepted"
REJECTED = "rejected"


@dataclass
class _Candidate:
    index: int
    name: str
    data: bytes
    check: FileCheck


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


def upload_cvs(uploader, project, files):
    """`files` are (name, size, read) triples in the order sent. Returns one result per file,
    in the same order."""
    require_editable(project)
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
        _accept(uploader, project, candidates, results)
    return results


def _accept(uploader, project, candidates, results):
    saved_keys = []
    try:
        with transaction.atomic():
            # One upload at a time per company, so the limits below cannot be passed together.
            Company.objects.select_for_update().get(pk=project.company_id)
            in_project = CvFile.objects.filter(project=project).count()
            split = split_batch(project.company_id, candidates, in_project)
            for skipped in split.skipped:
                results[skipped.file.index] = _result(
                    skipped.file.name, REJECTED, skipped.code, skipped.message, skipped.prompt
                )
            for candidate in split.accepted:
                cv_id = uuid.uuid4()
                key = storage.key_for_cv(project.company_id, cv_id)
                storage.save_file(key, candidate.data)
                saved_keys.append(key)
                CvFile.objects.create(
                    id=cv_id,
                    company_id=project.company_id,
                    project=project,
                    original_name=safe_file_name(candidate.name),
                    file_type=candidate.check.file_type,
                    page_count=candidate.check.page_count,
                    size_bytes=len(candidate.data),
                    storage_key=key,
                    uploaded_by=uploader,
                )
                usage.accept_cv(project.company_id, cv_id, project.pk)
                results[candidate.index] = _result(
                    candidate.name, ACCEPTED, notice=candidate.check.notice
                )
    except Exception:
        for key in saved_keys:  # nothing was recorded, so no file may stay behind
            storage.delete_file(key)
        raise


def _remove_for_project(company_id, project_id):
    """Deletes the project's files from storage and their records. The usage ledger keeps
    its history."""
    for key in CvFile.objects.filter(company_id=company_id, project_id=project_id).values_list(
        "storage_key", flat=True
    ):
        storage.delete_file(key)
    CvFile.objects.filter(company_id=company_id, project_id=project_id).delete()


register_project_data("CvFile", _remove_for_project)
