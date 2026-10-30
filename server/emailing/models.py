import uuid

from django.db import models
from django.db.models import Q

from core.field_protection import normalize_email
from core.protected_fields import EncryptedTextField, LookupHashField


class OutgoingEmail(models.Model):
    """An email waiting to be sent, and afterwards a record that it was handled.

    Addresses and message text are personal data and the links hold one-time tokens, so they
    are stored encrypted and wiped as soon as the email is sent or given up on.
    """

    class Status(models.TextChoices):
        QUEUED = "queued"
        SENT = "sent"
        FAILED = "failed"
        SUPPRESSED = "suppressed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.CharField(max_length=50)
    to_address = EncryptedTextField(purpose="outgoing_email.to_address")
    subject = EncryptedTextField(purpose="outgoing_email.subject")
    text_body = EncryptedTextField(purpose="outgoing_email.text_body")
    html_body = EncryptedTextField(purpose="outgoing_email.html_body")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    # Only the kind of error (such as "SMTPServerDisconnected"): provider messages can quote
    # the address.
    last_error = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["queued", "sent", "failed", "suppressed"]),
                name="outgoingemail_status_is_known",
            ),
        ]


class LinkToken(models.Model):
    """The secret in an email link. Random, used once, expires, and kept only as a hash, so a
    copy of the database cannot be used to open anyone's link. One purpose per token: a
    reset link can never verify an email."""

    class Purpose(models.TextChoices):
        VERIFY_EMAIL = "verify_email"
        RESET_PASSWORD = "reset_password"
        TEAM_INVITE = "team_invite"

    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    # The person (or invitation) it is for; the purpose says which table that is.
    subject_id = models.BigIntegerField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(purpose__in=["verify_email", "reset_password", "team_invite"]),
                name="linktoken_purpose_is_known",
            ),
        ]


class BouncedAddress(models.Model):
    """An address the provider said cannot receive email, or whose owner complained.
    Nothing is sent to it again."""

    class Kind(models.TextChoices):
        HARD_BOUNCE = "hard_bounce"
        COMPLAINT = "complaint"

    address = EncryptedTextField(purpose="bounced_address.address")
    address_lookup = LookupHashField(
        of="address", purpose="bounced_address.address", normalize=normalize_email
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["address_lookup"], name="bounced_address_is_unique"),
            models.CheckConstraint(
                condition=Q(kind__in=["hard_bounce", "complaint"]),
                name="bouncedaddress_kind_is_known",
            ),
        ]
