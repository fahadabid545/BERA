from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=200, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="companies"
    )
