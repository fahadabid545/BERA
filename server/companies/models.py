import secrets

from django.db import models
from django.db.models import Q

from core.errors import AppError
from core.field_protection import normalize_email
from core.models import CompanyOwnedModel, PersonAccount
from core.protected_fields import EncryptedTextField, LookupHashField

from .countries import OTHER_COUNTRY


def company_deletion_blocked():
    return AppError(
        "company_deletion_blocked",
        "A company can only be deleted through the deletion flow.",
        status_code=403,
    )


class CompanyQuerySet(models.QuerySet):
    def delete(self):
        raise company_deletion_blocked()


class Company(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"

    name = models.CharField(max_length=200)
    country = models.CharField(max_length=2, default=OTHER_COUNTRY)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    # When on, every member must have two-step verification (set up at their next login).
    require_two_step = models.BooleanField(default=False)

    objects = CompanyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "suspended"]), name="company_status_is_known"
            ),
        ]

    def delete(self, *args, **kwargs):
        # The deletion flow (its own ticket) will be the one allowed way. Until then nothing
        # deletes a company, and the protected links below stop it even if this is bypassed.
        raise company_deletion_blocked()


class CompanyUser(PersonAccount):
    class Role(models.TextChoices):
        OWNER = "owner"
        MEMBER = "member"

    class Status(models.TextChoices):
        ACTIVE = "active"
        BLOCKED = "blocked"
        REMOVED = "removed"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="users")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    email_verified = models.BooleanField(default=False)
    # When the person ticked the Terms and Privacy Policy at sign-up (or accepted an invite).
    terms_accepted_at = models.DateTimeField(null=True)
    # Two-step verification. The secret is saved when setup starts and only counts once
    # `two_step_enabled` is true, after the person proved their app shows the right codes.
    two_step_secret = EncryptedTextField(purpose="companyuser.two_step_secret", default="")
    two_step_enabled = models.BooleanField(default=False)
    # The newest 30-second step already used, so one code cannot be used twice.
    two_step_last_step = models.BigIntegerField(null=True)

    class Meta:
        constraints = [
            PersonAccount.email_is_normalised_constraint("companyuser"),
            # One address is one person, in one company, whatever its status.
            models.UniqueConstraint(fields=["email"], name="companyuser_email_is_unique"),
            # At most one owner per company; creating a company always adds the owner.
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(role="owner"),
                name="company_has_one_owner",
            ),
            models.CheckConstraint(
                condition=Q(role__in=["owner", "member"]), name="companyuser_role_is_known"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "blocked", "removed"]),
                name="companyuser_status_is_known",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and self._would_leave_the_company_without_an_owner():
            raise AppError(
                "owner_required",
                "A company must keep its owner. Transfer ownership first.",
                status_code=409,
            )
        super().save(*args, **kwargs)

    def _would_leave_the_company_without_an_owner(self):
        was_owner = CompanyUser.objects.filter(pk=self.pk, role=self.Role.OWNER).exists()
        return was_owner and (self.role != self.Role.OWNER or self.status == self.Status.REMOVED)


def new_token_subject():
    """What the invitation's link tokens refer to. LinkToken keeps whole numbers, while an
    invitation's own identifier is random text, so it also has a random number (62 bits, and
    unique) that is never shown to anyone."""
    return secrets.randbits(62)


class Invitation(CompanyOwnedModel):
    """An invitation to join a company, waiting to be accepted. The link in the email is a
    shared `LinkToken` (purpose team_invite) that refers to the invitation by `token_subject`."""

    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        REVOKED = "revoked"

    # Encrypted, and found through the hash (see core/protected_fields.py).
    email = EncryptedTextField(purpose="invitation.email")
    email_lookup = LookupHashField(
        of="email", purpose="invitation.email", normalize=normalize_email
    )
    invited_by = models.ForeignKey(
        CompanyUser, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    token_subject = models.BigIntegerField(unique=True, default=new_token_subject, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # One open invitation per address in a company; invite again after it ended.
            models.UniqueConstraint(
                fields=["company", "email_lookup"],
                condition=Q(status="pending"),
                name="invitation_one_pending_per_email",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "accepted", "revoked"]),
                name="invitation_status_is_known",
            ),
        ]
