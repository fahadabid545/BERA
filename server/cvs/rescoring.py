"""Re-scoring: bringing scored candidates up to date after the requirements change.

- A changed weight, kind, order, the split or the threshold needs no AI: the stored results are
  recombined at once (`scoring.recalculate_project`).
- A new requirement, or one whose wording changed, needs judging again, and only that one: each
  scored CV is put back through the pipeline, which reads the stored file again (no AI), guards
  the text, and sends only the requirements without a current result to the AI (see
  `evaluation.py`). The profile and every other result are kept.
- Before anything is saved the person sees how many CVs will run and the approximate cost
  (`estimate`), and a change that would pass the monthly AI token cap is refused.
- Until a candidate has been judged again its score is marked Outdated. If the AI fails for a
  CV, the CV fails with a reason (it can be retried) and its old score stays, marked Outdated.
  Re-scoring never counts a CV again against the plan's CV limits.
"""

from decimal import Decimal

from django.utils import timezone

from ai.costs import price_call
from plans.limits import check_ai_allowed, prompt_kind
from platform_settings.service import get_setting
from projects.models import Requirement

from .models import Candidate, CandidateScore, CvFile
from .processing import kick

BLOCKED_CODE = "rescoring_ai_not_allowed"


def changed_texts(project, items):
    """How many of the new list's items need judging: new ones, and ones whose text changed.
    `items` are dicts with `text` and, for an existing requirement, `id`."""
    stored = {str(r.pk): r.text for r in Requirement.objects.filter(project=project)}
    return sum(1 for item in items if stored.get(str(item.get("id"))) != item["text"])


def _scored_candidates(project):
    return Candidate.objects.filter(project=project, score__isnull=False)


def estimate(project, items):
    """What re-scoring would run: the scored CVs, the changed requirements and the approximate
    tokens and cost, and whether AI work is allowed."""
    changed = changed_texts(project, items)
    cvs = _scored_candidates(project).count()
    per_token = get_setting("estimate.characters_per_token")
    stored = {str(r.pk): r.text for r in Requirement.objects.filter(project=project)}
    changed_tokens = sum(
        -(-len(item["text"]) // per_token)
        for item in items
        if stored.get(str(item.get("id"))) != item["text"]
    )
    tokens_in = get_setting("estimate.scoring_prompt_tokens") + get_setting(
        "estimate.cv_text_tokens"
    )
    tokens_in = (tokens_in + changed_tokens) * cvs
    tokens_out = get_setting("estimate.scoring_output_tokens_per_requirement") * changed * cvs
    cost = cvs * price_call(
        project.scoring_model,
        (tokens_in // cvs) if cvs else 0,
        (tokens_out // cvs) if cvs else 0,
    )
    company_id = project.company_id
    allowed = check_ai_allowed(company_id)
    blocked = bool(cvs and changed) and not allowed.allowed
    return {
        "approximate": True,
        "cvs": cvs if changed else 0,
        "requirements": changed,
        "tokens_total": tokens_in + tokens_out if changed else 0,
        "estimated_cost": Decimal(cost) if changed else Decimal(0),
        "blocked": blocked,
        "code": BLOCKED_CODE,
        "message": allowed.message if blocked else "",
        "prompt": prompt_kind(company_id) if blocked else None,
    }


def start(project):
    """After the requirements were saved: marks the scored candidates Outdated and puts their
    finished CVs back in line. Returns how many CVs were queued."""
    scored_ids = list(_scored_candidates(project).values_list("pk", flat=True))
    CandidateScore.objects.filter(candidate_id__in=scored_ids).update(outdated=True)
    queued = CvFile.objects.filter(
        project=project, status=CvFile.Status.DONE, candidate__in=scored_ids
    ).update(
        status=CvFile.Status.WAITING,
        attempts=0,
        failure_reason="",
        next_attempt_at=timezone.now(),
        finished_at=None,
        claim_token=None,
    )
    return queued


def wake(queued):
    """Wakes the workers for the queued CVs; called after the transaction has ended."""
    kick(queued)
