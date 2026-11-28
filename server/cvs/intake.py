"""The project's rules for a candidate's first score: shortlist a strong match at once, or reject
one that is clearly too low. They act once, on the first score only, so re-scoring never undoes
what a person has since decided. A move made here is in the stage history as a project rule, and
the person can move the candidate back by hand."""

from .models import Candidate, StageChange


def _move(candidate, stage):
    StageChange.objects.create(
        company_id=candidate.company_id,
        candidate=candidate,
        from_stage=candidate.stage,
        to_stage=stage,
        changed_by=None,
    )
    Candidate.objects.filter(pk=candidate.pk).update(stage=stage)
    candidate.stage = stage


def apply_intake_rules(candidate, score, strong_match_threshold):
    """Moves a new candidate by the project's rules. Rejecting wins over shortlisting."""
    if candidate.stage != Candidate.Stage.NEW:
        return
    project = candidate.project
    if project.auto_reject_below is not None and score < project.auto_reject_below:
        _move(candidate, Candidate.Stage.REJECTED)
    elif project.auto_shortlist and score >= strong_match_threshold:
        _move(candidate, Candidate.Stage.SHORTLISTED)
