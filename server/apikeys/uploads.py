"""Uploading CVs through the API. The files go through exactly the same path as the company
panel (`cvs.service.upload_cvs`): the same file checks, limits, usage counting and fair
processing. On top of that, an `Idempotency-Key` header makes a repeated request safe: the first
answer is sent again and nothing is counted or processed twice."""

import hashlib
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from companies.models import CompanyUser
from core.errors import AppError, form_error
from cvs.service import batch_id_from, upload_cvs
from platform_settings.service import get_setting

from .models import IDEMPOTENCY_KEY_LENGTH, ApiIdempotency, ApiKey

KEY_PATTERN = re.compile(rf"[A-Za-z0-9_-]{{1,{IDEMPOTENCY_KEY_LENGTH}}}")
CHUNK_BYTES = 64 * 1024


def checked_idempotency_key(value):
    if value is None:
        return None
    if not KEY_PATTERN.fullmatch(value):
        raise form_error(
            {"Idempotency-Key": f"Use 1 to {IDEMPOTENCY_KEY_LENGTH} letters, digits, - or _."}
        )
    return value


def fingerprint_of(project, batch_id, sent):
    """The same request has the same fingerprint: project, batch and every file's name and
    content. Reads each file through in pieces and rewinds it."""
    digest = hashlib.sha256()
    digest.update(f"{project.pk}|{batch_id}".encode())
    for file in sent:
        content = hashlib.sha256()
        for chunk in file.chunks(CHUNK_BYTES):
            content.update(chunk)
        file.seek(0)
        digest.update(f"|{file.name}|{content.hexdigest()}".encode())
    return digest.hexdigest()


def _forget_old(key):
    cutoff = timezone.now() - timedelta(hours=get_setting("api.idempotency_hours"))
    ApiIdempotency.objects.filter(api_key=key, created_at__lt=cutoff).delete()


def _reserve(key, idempotency_key, fingerprint):
    """(row, replay): the new reservation, or the earlier one this request repeats."""
    try:
        with transaction.atomic():
            row = ApiIdempotency.objects.create(
                company_id=key.company_id,
                api_key=key,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
        return row, False
    except IntegrityError:
        return ApiIdempotency.objects.get(api_key=key, idempotency_key=idempotency_key), True


def _repeat(row, fingerprint):
    if row.fingerprint != fingerprint:
        raise AppError(
            "idempotency_key_reused",
            "This Idempotency-Key was already used for a different request.",
            status_code=422,
        )
    if row.response is None:
        raise AppError(
            "request_in_progress",
            "The first request with this Idempotency-Key is still running. Try again shortly.",
            status_code=409,
        )
    return row.response


def upload(principal, project, sent, batch, idempotency_key):
    """(body, replayed). Without an Idempotency-Key every request is handled as it comes."""
    batch_id = batch_id_from(batch)
    uploader = CompanyUser.objects.get(pk=principal.uploader_id)
    files = [(file.name, file.size, file.read) for file in sent]
    if idempotency_key is None:
        return {"results": upload_cvs(uploader, project, files, batch_id)}, False

    key = ApiKey.objects.get(pk=principal.key_id)
    _forget_old(key)
    fingerprint = fingerprint_of(project, batch_id, sent)
    row, replay = _reserve(key, idempotency_key, fingerprint)
    if replay:
        return _repeat(row, fingerprint), True
    try:
        body = {"results": upload_cvs(uploader, project, files, batch_id)}
    except BaseException:
        row.delete()  # nothing was accepted, so the same request may be tried again
        raise
    row.response = body
    row.save(update_fields=["response"])
    return body, False
