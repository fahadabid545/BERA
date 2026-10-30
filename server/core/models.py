import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Trim

from .field_protection import normalize_email


class PersonAccount(models.Model):
    """What every kind of account has. Each kind (company user, admin user) is its own table
    with its own credentials: nothing is stored in a table both kinds share.

    The email is kept trimmed and lower case, so "Jo@Example.com " and "jo@example.com" are
    one address. The password is kept only as a strong one-way hash.
    """

    name = models.CharField(max_length=200)
    email = models.EmailField(max_length=254)
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    @staticmethod
    def email_is_normalised_constraint(label):
        return models.CheckConstraint(
            condition=Q(email=Lower(Trim("email"))), name=f"{label}_email_is_normalised"
        )

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def set_unusable_password(self):
        """For an invited person who has not chosen a password yet: no password matches."""
        self.password_hash = make_password(None)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)


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
