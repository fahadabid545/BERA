from django.db import models
from django.db.models import Q

from core.field_protection import normalize_email
from core.models import CompanyOwnedModel
from core.protected_fields import EncryptedTextField, LookupHashField


class FreeAccessInvite(models.Model):
    """Something a super admin made to give free access: an email address, or a code to share.
    Not company data: it exists before any company uses it.

    Kinds: a beta email or a beta code (limited access for a few days, see `entitlement.py`) and a
    permitted email (a plan's full limits, free, until taken back). Switching an invite off stops
    new use; the access it already gave is a separate record (`FreeAccess`)."""

    class Kind(models.TextChoices):
        BETA_EMAIL = "beta_email"
        BETA_CODE = "beta_code"
        PERMITTED_EMAIL = "permitted_email"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    label = models.CharField(max_length=100, blank=True)  # the admin's own note
    email = EncryptedTextField(purpose="free_access_invite.email", blank=True)
    email_lookup = LookupHashField(
        of="email", purpose="free_access_invite.email", normalize=normalize_email
    )
    code_hash = models.CharField(max_length=64, null=True, unique=True)  # never the code itself
    plan = models.ForeignKey("plans.Plan", null=True, on_delete=models.PROTECT, related_name="+")
    access_days = models.PositiveIntegerField(null=True)  # beta: days of access from joining
    max_uses = models.PositiveIntegerField(null=True)  # code: how many companies may join
    redeem_until = models.DateTimeField(null=True)  # code: the last moment it may be used
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="beta_email", email_lookup__isnull=False, access_days__isnull=False)
                    | Q(
                        kind="beta_code",
                        code_hash__isnull=False,
                        access_days__isnull=False,
                        max_uses__isnull=False,
                    )
                    | Q(kind="permitted_email", email_lookup__isnull=False, plan__isnull=False)
                ),
                name="free_access_invite_has_what_its_kind_needs",
            )
        ]


class FreeAccess(CompanyOwnedModel):
    """Free access one company has, from one invite. It is its own record: it never touches the
    company's subscription or any admin account, so taking it away leaves a paid plan and an admin
    role as they were. Active means not revoked and not past its end."""

    class Kind(models.TextChoices):
        BETA = "beta"
        PERMITTED = "permitted"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    invite = models.ForeignKey(FreeAccessInvite, on_delete=models.PROTECT, related_name="grants")
    plan = models.ForeignKey("plans.Plan", null=True, on_delete=models.PROTECT, related_name="+")
    started_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True)  # none for permitted access: it ends when revoked
    revoked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # An invite gives one company access once; a revoked access is never given again.
            models.UniqueConstraint(fields=["company", "invite"], name="one_access_per_invite"),
            models.CheckConstraint(
                condition=Q(kind="permitted", plan__isnull=False, ends_at__isnull=True)
                | Q(kind="beta", plan__isnull=True, ends_at__isnull=False),
                name="free_access_has_what_its_kind_needs",
            ),
        ]
