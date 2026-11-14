"""Calculating and saving a candidate's ATS score as a pipeline step (slot `ats_score`).

It uses no AI, so it costs nothing and runs even when AI scoring is paused. The score is kept per
candidate and made again only when the job description has changed, so a retry or a re-scoring
that changes nothing gives the same stored result."""

import hashlib

from .ats import RULES_VERSION, score_cv
from .ats_layout import layout_of
from .models import AtsScore
from .processing import StepContext, register_step


def _hash_of(job_description):
    return hashlib.sha256(job_description.encode()).hexdigest()


def calculate_ats_score(candidate, text, file_data):
    """The saved `AtsScore` of the candidate, made now unless one exists for the same job
    description and rules."""
    project = candidate.project
    description_hash = _hash_of(project.job_description)
    saved = AtsScore.objects.filter(candidate=candidate).first()
    if (
        saved
        and saved.job_description_hash == description_hash
        and saved.rules_version == RULES_VERSION
    ):
        return saved
    cv_file = candidate.cv_file
    layout = layout_of(cv_file.file_type, file_data, cv_file.page_count)
    result = score_cv(text, project.job_description, layout)
    reasons = [
        {"code": reason.code, "message": reason.message, "points": reason.points}
        for reason in result.reasons
    ]
    score, _ = AtsScore.objects.update_or_create(
        candidate=candidate,
        defaults={
            "company_id": candidate.company_id,
            "score": result.score,
            "reasons": reasons,
            "job_description_hash": description_hash,
            "rules_version": RULES_VERSION,
        },
    )
    return score


def score_for_ats(context: StepContext):
    """Slot `ats_score`: reads the original text and file, because the contact details and the
    pictures count here. Only the score and generic reasons are stored."""
    calculate_ats_score(
        context.cv_file.candidate, context.state["text"], context.state["file_data"]
    )


register_step("ats_score", score_for_ats)
