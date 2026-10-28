from django.db import models


class PlatformSetting(models.Model):
    """An admin's changed value. A setting without a row uses its default."""

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)
