"""Avoiding the same CV twice.

1. **An identical file** (same bytes) already in the project is skipped at upload with a notice
   and never counted (`split_identical`).
2. **A likely same person** (an email or phone number found in the CV that another CV in the
   project also has) is found after the text is read (`review_likely_duplicate`, called by
   processing) and flagged for review. A flagged CV does not count against the limits once
   scored until the person keeps it (`counts_toward_limits`); discarding it removes it and
   gives its allowance back.

Emails and phone numbers are personal data, so only keyed hashes of them are stored."""

import hashlib
import re

from django.db import transaction
from django.db.models import Q

from companies.models import Company
from core.errors import AppError
from core.field_protection import lookup_hash, normalize_email
from platform_settings.service import get_setting
from projects.service import require_editable
from usage import service as usage

from .models import CvFile

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)
PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{4,}\d")
EMAIL_PURPOSE = "cv.email"
PHONE_PURPOSE = "cv.phone"
DUPLICATE_FILE = "duplicate_file"
DUPLICATE_FILE_MESSAGE = "This file is already in the project, so it was skipped."
NOT_FLAGGED_CODE = "not_flagged"


def content_hash(data):
    return hashlib.sha256(data).hexdigest()


def split_identical(project, candidates):
    """Splits `candidates` (each with `.data`) into those to go on with and those that repeat
    a file already in the project or earlier in the same upload. Call it with the company
    locked, so two uploads at once cannot both add the same file."""
    known = set(
        CvFile.objects.filter(project=project, content_hash__isnull=False).values_list(
            "content_hash", flat=True
        )
    )
    fresh, repeated = [], []
    for candidate in candidates:
        candidate.content_hash = content_hash(candidate.data)
        if candidate.content_hash in known:
            repeated.append(candidate)
        else:
            known.add(candidate.content_hash)
            fresh.append(candidate)
    return fresh, repeated


def contact_hashes_in(text):
    """Keyed hashes of the distinct emails and phone numbers in the text of a CV."""
    found = {lookup_hash(normalize_email(email), EMAIL_PURPOSE) for email in EMAIL.findall(text)}
    size = get_setting("duplicates.phone_digits")
    for phone in PHONE.findall(text):
        digits = "".join(character for character in phone if character.isdigit())
        if len(digits) >= size:
            found.add(lookup_hash(digits[-size:], PHONE_PURPOSE))
    return sorted(found)


def review_likely_duplicate(cv_file, text):
    """Looks for another CV of the project sharing an email or phone number with this one (from
    its text), remembers this CV's contacts, and flags it for review when there is a match.
    Returns the CV it looks like, or None. A CV the person already decided to keep is never
    flagged again."""
    hashes = contact_hashes_in(text)
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=cv_file.company_id)
        cv_file.refresh_from_db()
        cv_file.contact_hashes = hashes
        match = None
        if hashes and cv_file.review != CvFile.Review.KEPT:
            shared = Q()
            for value in hashes:
                shared |= Q(contact_hashes__contains=[value])
            match = (
                CvFile.objects.filter(project_id=cv_file.project_id, company_id=cv_file.company_id)
                .exclude(pk=cv_file.pk)
                .filter(shared)
                .order_by("created_at")
                .first()
            )
        if match:
            cv_file.review, cv_file.duplicate_of = CvFile.Review.FLAGGED, match
        cv_file.save(update_fields=["contact_hashes", "review", "duplicate_of"])
    return match


def counts_toward_limits(cv_file):
    """False while a CV waits for the person's decision: the scoring pipeline counts a scored CV
    (`usage.mark_scored`) only when this is true, and counts it when it is kept."""
    return cv_file.review != CvFile.Review.FLAGGED


def _flagged(cv_file):
    if cv_file.review != CvFile.Review.FLAGGED:
        raise AppError(NOT_FLAGGED_CODE, "This CV is not waiting for a decision.", status_code=409)


def keep_flagged_cv(cv_file):
    """The person says it is a different CV after all: it stays and now counts."""
    with transaction.atomic():
        cv_file = CvFile.objects.select_for_update().get(pk=cv_file.pk)
        require_editable(cv_file.project)
        _flagged(cv_file)
        cv_file.review = CvFile.Review.KEPT
        cv_file.save(update_fields=["review"])
    return cv_file


def discard_flagged_cv(cv_file):
    """The person says it is a repeat: its file and record are removed and, as it was never
    scored, its allowance is given back."""
    from .service import remove_cv_file  # the upload service imports this module

    with transaction.atomic():
        cv_file = CvFile.objects.select_for_update().get(pk=cv_file.pk)
        require_editable(cv_file.project)
        _flagged(cv_file)
        usage.mark_failed(cv_file.company_id, cv_file.pk)
        remove_cv_file(cv_file)
