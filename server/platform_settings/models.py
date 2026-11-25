from django.db import models


class PlatformSetting(models.Model):
    """An admin's changed value. A setting without a row uses its default."""

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)


class LegalReview(models.Model):
    """Whether the Terms and Privacy text was reviewed: one row. The reviewer's name is kept
    here and never in the audit log (see legal_review.py)."""

    reviewed = models.BooleanField(default=False)
    reviewer_name = models.CharField(max_length=100, blank=True)
    reviewed_on = models.DateField(null=True)
    # Which text the review was of; a different version means it no longer applies.
    reviewed_version = models.CharField(max_length=40, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
