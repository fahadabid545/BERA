from django.db import models
from django.db.models import Q

from core.errors import AppError
from core.models import PersonAccount

# ISO 3166 "unknown or unspecified"; the sign-up screen shows it as "Other".
OTHER_COUNTRY = "ZZ"


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
