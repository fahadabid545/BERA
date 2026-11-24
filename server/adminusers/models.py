from django.db import models
from django.db.models import Q

from companies.models import new_token_subject
from core.field_protection import normalize_email
from core.models import PersonAccount
from core.protected_fields import EncryptedTextField, LookupHashField


class AdminUser(PersonAccount):
    """Staff of the platform. Not tied to any company, and never a company user."""

    class Role(models.TextChoices):
        SUPER = "super"
        SUPPORT = "support"

    class Status(models.TextChoices):
        ACTIVE = "active"
        BLOCKED = "blocked"
        REMOVED = "removed"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SUPPORT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    # Two-step verification is required for every admin. The secret is saved when setup starts
    # and only counts once `two_step_enabled` is true. Admins get no recovery codes: another
    # super admin resets a lost device.
    two_step_secret = EncryptedTextField(purpose="adminuser.two_step_secret", default="")
    two_step_enabled = models.BooleanField(default=False)
    two_step_last_step = models.BigIntegerField(null=True)

    class Meta:
        constraints = [
            PersonAccount.email_is_normalised_constraint("adminuser"),
            models.UniqueConstraint(fields=["email"], name="adminuser_email_is_unique"),
            models.CheckConstraint(
                condition=Q(role__in=["super", "support"]), name="adminuser_role_is_known"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "blocked", "removed"]),
                name="adminuser_status_is_known",
            ),
        ]


class AdminInvitation(models.Model):
    """A super admin's invitation for someone to become an admin, waiting to be accepted. The link
    in the email is a shared `LinkToken` (purpose admin_invite) that refers to the invitation by
    `token_subject`. The invitee chooses the password when accepting, and sets up two-step
    verification at their first sign-in, like every admin."""

    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        REVOKED = "revoked"

    name = models.CharField(max_length=200)
    # Encrypted, and found through the hash (see core/protected_fields.py).
    email = EncryptedTextField(purpose="admininvitation.email")
    email_lookup = LookupHashField(
        of="email", purpose="admininvitation.email", normalize=normalize_email
    )
    role = models.CharField(max_length=20, choices=AdminUser.Role.choices)
    invited_by = models.ForeignKey(
        AdminUser, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    token_subject = models.BigIntegerField(unique=True, default=new_token_subject, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # One open invitation per address; invite again after it ended.
            models.UniqueConstraint(
                fields=["email_lookup"],
                condition=Q(status="pending"),
                name="admininvitation_one_pending_per_email",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "accepted", "revoked"]),
                name="admininvitation_status_is_known",
            ),
            models.CheckConstraint(
                condition=Q(role__in=["super", "support"]), name="admininvitation_role_is_known"
            ),
        ]
