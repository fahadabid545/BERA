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
    prompt_version = models.PositiveIntegerField()  # the reading prompt version used
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


class RequirementResult(CompanyOwnedModel):
    """How one candidate's CV meets one requirement: a verdict, a short quote that really is in
    the CV, and a confidence. Score calculation works from these. `requirement_text` is what the
    CV was judged against, so an edited requirement is judged again and an unchanged one never
    is."""

    class Verdict(models.TextChoices):
        MET = "met"
        PARTLY_MET = "partly_met"
        MISSING = "missing"

    class Confidence(models.TextChoices):
        HIGH = "high"
        MEDIUM = "medium"
        LOW = "low"

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="results")
    requirement = models.ForeignKey(
        "projects.Requirement", on_delete=models.CASCADE, related_name="results"
    )
    requirement_text = models.TextField()
    verdict = models.CharField(max_length=20, choices=Verdict.choices)
    evidence = models.TextField(blank=True)  # empty exactly when the verdict is missing
    confidence = models.CharField(max_length=10, choices=Confidence.choices)
    model = models.CharField(max_length=100)
    prompt_version = models.PositiveIntegerField()  # the scoring prompt version used
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "requirement"], name="one_result_per_candidate_requirement"
            ),
            models.CheckConstraint(
                condition=models.Q(verdict="missing", evidence="")
                | (~models.Q(verdict="missing") & ~models.Q(evidence="")),
                name="evidence_exactly_when_not_missing",
            ),
        ]


class AtsScore(CompanyOwnedModel):
    """How well an applicant tracking system would read the CV (see `ats.py`): a number from 0 to
    100 and the reasons that lowered it. It is kept apart from the AI score and made without AI.
    `job_description_hash` says which job description it was measured against, so an edited
    description is measured again; `rules_version` says which rules made it."""

    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name="ats_score")
    score = models.PositiveSmallIntegerField()
    reasons = models.JSONField(default=list)
    job_description_hash = models.CharField(max_length=64)
    rules_version = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__lte=100), name="ats_score_is_at_most_100"
            ),
        ]


class CandidateScore(CompanyOwnedModel):
    """The final score of one candidate (see `scoring.py`): 0 to 100 with one decimal, the grade
    it falls in, and the two group scores it was combined from. It is worked out by the system's
    own rules from the requirement results, never by the AI. `capped` says the cap on a missing
    must-have lowered it. Only the requirements count: the ATS score and the extra factors stay
    separate."""

    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name="score")
    score = models.DecimalField(max_digits=4, decimal_places=1)
    grade = models.CharField(max_length=1)
    must_score = models.DecimalField(max_digits=4, decimal_places=1, null=True)
    nice_score = models.DecimalField(max_digits=4, decimal_places=1, null=True)
    capped = models.BooleanField(default=False)
    # The recommendation and insights (see `recommendation.py`), worked out with the score.
    label = models.CharField(max_length=20, default="not_recommended")
    borderline = models.BooleanField(default=False)
    strengths = models.JSONField(default=list)
    risks = models.JSONField(default=list)
    interview_questions = models.JSONField(default=list)
    guide_note = models.CharField(max_length=200, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(label__in=["strong_match", "possible", "not_recommended"]),
                name="score_label_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(score__gte=0, score__lte=100), name="score_is_0_to_100"
            ),
            models.CheckConstraint(
                condition=models.Q(grade__in=["A", "B", "C", "D", "E"]),
                name="score_grade_is_known",
            ),
        ]


class ExtraFactorValues(CompanyOwnedModel):
    """The extra scoring factors of one candidate (see `extra_factors.py`): for each factor a
    whole number from 0 to 100 or null for "Not found", with a short explanation. All are stored,
    switched on or not. `basis_hash` says which job expectations they were measured against."""

    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name="factors")
    values = models.JSONField(default=dict)
    basis_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
