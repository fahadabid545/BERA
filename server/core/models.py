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


class RateCounter(models.Model):
    """How many times something happened in one fixed time window (see core/rate_limits.py)."""

    # A hash of rule and source, so no address or email is stored readably.
    key = models.CharField(max_length=64)
    window_start = models.BigIntegerField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "window_start"], name="one_counter")]


class BlockedSource(models.Model):
    """A source blocked for repeated abuse until `blocked_until`."""

    key = models.CharField(max_length=64, unique=True)
    blocked_until = models.DateTimeField()
