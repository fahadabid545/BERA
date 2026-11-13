from django.db import models

from core.models import CompanyOwnedModel


class CvFile(CompanyOwnedModel):
    """One uploaded CV. Its id is the CV id the usage counting works with. The file itself is
    kept by `cvs/storage.py` under `storage_key`; the name is only for showing to people."""

    class Status(models.TextChoices):
        WAITING = "waiting"  # accepted; Background processing takes it from here

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="cv_files"
    )
    original_name = models.TextField()
    file_type = models.CharField(max_length=20)
    size_bytes = models.PositiveBigIntegerField()
    storage_key = models.TextField(unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    uploaded_by = models.ForeignKey(
        "companies.CompanyUser", on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
