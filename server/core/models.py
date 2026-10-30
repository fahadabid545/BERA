import uuid

from django.db import models


class CompanyOwnedModel(models.Model):
    """Base for everything that belongs to one company (projects, candidates, files, reports...).

    The identifier is random, so addresses and requests never show 1, 2, 3 to guess from.
    Data requests read these models through `core.scoping`, which only ever sees one company.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True
