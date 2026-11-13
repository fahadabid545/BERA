from django.db import models

from core.models import CompanyOwnedModel


class CvFile(CompanyOwnedModel):
    """One uploaded CV. Its id is the CV id the usage counting works with. The file itself is
    kept by `cvs/storage.py` under `storage_key`; the name is only for showing to people."""

    class Status(models.TextChoices):
        WAITING = "waiting"  # accepted; Background processing takes it from here

    class Review(models.TextChoices):
        NONE = "none"
        FLAGGED = "flagged"  # looks like the same person as `duplicate_of`; waiting for a decision
        KEPT = "kept"  # the person decided to keep it

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="cv_files"
    )
    original_name = models.TextField()
    file_type = models.CharField(max_length=20)
    size_bytes = models.PositiveBigIntegerField()
    page_count = models.PositiveIntegerField(null=True)  # None when the file does not say
    storage_key = models.TextField(unique=True)
    # A hash of the file's bytes (never reversed), so an identical file is recognised.
    content_hash = models.CharField(max_length=64, null=True)
    # Keyed hashes of the emails and phone numbers found in the CV, never the values themselves.
    contact_hashes = models.JSONField(default=list)
    review = models.CharField(max_length=20, choices=Review.choices, default=Review.NONE)
    duplicate_of = models.ForeignKey("self", null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    uploaded_by = models.ForeignKey(
        "companies.CompanyUser", on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "content_hash"],
                condition=models.Q(content_hash__isnull=False),
                name="one_copy_of_a_file_per_project",
            ),
        ]
