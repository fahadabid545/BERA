from django.db import models


class KnowledgeDocument(models.Model):
    """A public product document the website chatbot may use (see `documents.py`).

    Only the extracted text is kept, never the original file. Deliberately not a company-owned
    model and with no link to any company, candidate, project or CV table: this is public product
    information that an admin uploads, and no company data may ever be put into it."""

    name = models.CharField(max_length=200)
    file_type = models.CharField(max_length=10)
    size_bytes = models.PositiveBigIntegerField()  # the size of the file that was uploaded
    text = models.TextField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
