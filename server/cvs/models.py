from django.db import models
from django.utils import timezone

from core.models import CompanyOwnedModel
from core.protected_fields import EncryptedTextField


class CvFile(CompanyOwnedModel):
    """One uploaded CV. Its id is the CV id the usage counting works with. The file itself is
    kept by `cvs/storage.py` under `storage_key`; the name is only for showing to people."""

    class Status(models.TextChoices):
        WAITING = "waiting"  # accepted (or waiting for another try); processing takes it next
        READING = "reading"  # being read (text, then the AI)
        SCORING = "scoring"
        DONE = "done"
        FAILED = "failed"  # gave up; `failure_reason` says why and the person can retry
        CANCELLED = "cancelled"  # the batch was cancelled before this one started

    ACTIVE_STATUSES = (Status.WAITING, Status.READING, Status.SCORING)

    class Review(models.TextChoices):
        NONE = "none"
        FLAGGED = "flagged"  # looks like the same person as `duplicate_of`; waiting for a decision
        KEPT = "kept"  # the person decided to keep it

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="cv_files"
    )
    original_name = models.TextField()
    file_type = models.CharField(max_length=20)
    size_bytes = models.PositiveBigIntegerField()
    page_count = models.PositiveIntegerField(null=True)  # None when the file does not say
    storage_key = models.TextField(unique=True)
    # A hash of the file's bytes (never reversed), so an identical file is recognised.
    content_hash = models.CharField(max_length=64, null=True)
    # Keyed hashes of the emails and phone numbers found in the CV, never the values themselves.
    contact_hashes = models.JSONField(default=list)
    review = models.CharField(max_length=20, choices=Review.choices, default=Review.NONE)
    duplicate_of = models.ForeignKey("self", null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    # Processing (see processing.py). A worker claims a CV by giving it a fresh `claim_token`
    # and only the holder of that token may change it afterwards, so a worker that was
    # replaced (after a restart or a timeout) can never overwrite the new one.
    batch_id = models.UUIDField(null=True)  # the upload (drop) it arrived with
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    claim_token = models.UUIDField(null=True)
    failure_reason = models.TextField(blank=True)  # words for the person, never internals
    uploaded_by = models.ForeignKey(
        "companies.CompanyUser", on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "content_hash"],
                condition=models.Q(content_hash__isnull=False),
                name="one_copy_of_a_file_per_project",
            ),
        ]
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="cv_queue_lookup")]


class ProcessingTurn(CompanyOwnedModel):
    """When a company's CV last got a turn. The next turn goes to the company that waited the
    longest, so one large batch cannot hold up everyone else."""

    last_served_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company"], name="one_processing_turn_per_company")
        ]


class CvProfile(CompanyOwnedModel):
    """What the AI read from a CV, checked against the CV's text. Made once and reused: scoring
    and re-scoring work from it and never read the CV again. It holds no contact or personal
    details; those are in `CvContact`. The model and prompt version say how it was made."""

    cv_file = models.OneToOneField(CvFile, on_delete=models.CASCADE, related_name="profile")
    content = models.JSONField()
    model = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)


class CvContact(CompanyOwnedModel):
    """The contact details found in a CV, kept apart from the profile used for scoring so that
    they can never reach it. The four fields are encrypted in the database (see
    `core/protected_fields.py`); show them masked (`core/personal_data.py`) unless the full
    value is needed."""

    cv_file = models.OneToOneField(CvFile, on_delete=models.CASCADE, related_name="contact")
    name = EncryptedTextField(purpose="cv_contact.name", blank=True)
    email = EncryptedTextField(purpose="cv_contact.email", blank=True)
    phone = EncryptedTextField(purpose="cv_contact.phone", blank=True)
    address = EncryptedTextField(purpose="cv_contact.address", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Candidate(CompanyOwnedModel):
    """One person's CV in a project, created once the CV has been read (see `candidates.py`).
    It ties together the original file, the profile used for scoring and the contact details,
    and carries the stage. Scores and notes (later tickets) point at the candidate with a
    cascading link, so removing the candidate removes them too."""

    class Stage(models.TextChoices):
        NEW = "new"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="candidates"
    )
    cv_file = models.OneToOneField(CvFile, on_delete=models.CASCADE, related_name="candidate")
    profile = models.OneToOneField(CvProfile, on_delete=models.CASCADE, related_name="candidate")
    contact = models.OneToOneField(CvContact, on_delete=models.CASCADE, related_name="candidate")
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
