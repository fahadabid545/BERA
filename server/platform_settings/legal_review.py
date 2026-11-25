"""Whether the Terms and Privacy text was reviewed by a lawyer.

Only a super admin can say so, with the reviewer's name, the date of the review and the version
of the text that was reviewed. If the text changes afterwards the review no longer applies and
it goes back to "not reviewed" by itself. The launch checklist (BERA-184) calls `is_reviewed()`
and must refuse to pass while it is False. The public pages never show this status.
"""

from datetime import date

from django.db import transaction

from adminusers.models import AdminUser
from audit.service import record
from core.errors import AppError, form_error

from . import legal_documents
from .models import LegalReview

NOTHING_TO_REVIEW = (
    "Both the Terms and the Privacy text must be in place before they can be reviewed."
)


def _row():
    review, _ = LegalReview.objects.get_or_create(pk=1)
    return review


def _void_if_text_changed(review):
    """A review of other text is not a review of this text."""
    if review.reviewed and review.reviewed_version != legal_documents.current_version():
        review.reviewed = False
        review.save(update_fields=["reviewed"])
        record("admin.legal_review_reset", details={"version": legal_documents.current_version()})


def status():
    with transaction.atomic():
        review = LegalReview.objects.select_for_update().filter(pk=1).first() or _row()
        _void_if_text_changed(review)
    return {
        "reviewed": review.reviewed,
        "reviewer_name": review.reviewer_name,
        "reviewed_on": review.reviewed_on.isoformat() if review.reviewed_on else None,
        "reviewed_version": review.reviewed_version,
        "current_version": legal_documents.current_version(),
        "text_in_place": legal_documents.is_written(),
    }


def is_reviewed():
    return status()["reviewed"]


def mark_reviewed(admin: AdminUser, *, reviewer_name, reviewed_on=None):
    if not legal_documents.is_written():
        raise AppError("nothing_to_review", NOTHING_TO_REVIEW, status_code=409)
    reviewed_on = reviewed_on or date.today()
    if reviewed_on > date.today():
        raise form_error({"reviewed_on": "The review date cannot be in the future."})
    version = legal_documents.current_version()
    with transaction.atomic():
        review = LegalReview.objects.select_for_update().filter(pk=1).first() or _row()
        review.reviewed = True
        review.reviewer_name = reviewer_name
        review.reviewed_on = reviewed_on
        review.reviewed_version = version
        review.save()
        record("admin.legal_review_marked", actor=admin, details={"version": version})
    return status()


def clear_review(admin: AdminUser):
    with transaction.atomic():
        review = LegalReview.objects.select_for_update().filter(pk=1).first() or _row()
        if review.reviewed:
            review.reviewed = False
            review.save(update_fields=["reviewed"])
            record(
                "admin.legal_review_cleared",
                actor=admin,
                details={"version": review.reviewed_version},
            )
    return status()
