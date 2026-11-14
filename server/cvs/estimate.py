"""The cost estimate shown before CVs are processed.

An upload holds its CVs (Awaiting confirmation). The estimate says how many are held, the tokens
and money they are expected to use, and where that leaves the plan's limits and the monthly AI
token cap. The person then confirms (the CVs start) or cancels (they are removed and give their
allowance back). If the estimate would pass the token cap, confirming is refused with a message.

The figures are averages from platform settings (`estimate.*`), priced with the project's own
models, so they are always shown as approximate; the real use is only known after processing.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ai.costs import price_call
from companies.models import Company
from core.errors import AppError
from plans.limits import (
    CVS_PER_MONTH,
    CVS_PER_PROJECT,
    MONTHLY_AI_TOKEN_CAP,
    check_ai_allowed,
    limit_for,
    prompt_kind,
)
from platform_settings.service import get_setting
from projects.models import Requirement
from projects.service import require_editable
from usage import service as usage

from .models import CvFile
from .processing import kick

AWAITING = CvFile.Status.AWAITING_CONFIRMATION
OVER_CAP_CODE = "estimate_over_token_cap"
OVER_CAP_MESSAGE = (
    "These CVs are expected to use more AI than your plan has left this period. "
    "Cancel some of them, or raise your limit."
)
NOTHING_TO_CONFIRM_CODE = "nothing_to_confirm"
NOTHING_TO_CONFIRM_MESSAGE = "There are no CVs waiting for confirmation."


def _held(project, batch_id=None):
    held = CvFile.objects.filter(project=project, status=AWAITING)
    return held.filter(batch_id=batch_id) if batch_id is not None else held


def _tokens_for_one_cv(project):
    """(reading in, reading out, scoring in, scoring out) tokens expected for one CV."""
    per_token = get_setting("estimate.characters_per_token")
    texts = Requirement.objects.filter(project=project).values_list("text", flat=True)
    requirements = list(texts)
    requirement_tokens = sum(-(-len(text) // per_token) for text in requirements)
    cv_tokens = get_setting("estimate.cv_text_tokens")
    return (
        get_setting("estimate.reading_prompt_tokens") + cv_tokens,
        get_setting("estimate.reading_output_tokens"),
        get_setting("estimate.scoring_prompt_tokens") + cv_tokens + requirement_tokens,
        get_setting("estimate.scoring_output_tokens_per_requirement") * len(requirements),
    )


def _limit(company_id, name, used):
    return {"used": used, "limit": limit_for(company_id, name)}


def estimate(project, batch_id=None):
    """The estimate for the CVs of `project` held for confirmation (or one upload's)."""
    cvs = _held(project, batch_id).count()
    read_in, read_out, score_in, score_out = _tokens_for_one_cv(project)
    tokens_in, tokens_out = cvs * (read_in + score_in), cvs * (read_out + score_out)
    cost = cvs * (
        price_call(project.reading_model, read_in, read_out)
        + price_call(project.scoring_model, score_in, score_out)
    )
    company_id = project.company_id
    current = usage.current_usage(company_id)
    used_tokens = current["tokens_in"] + current["tokens_out"]
    cap = limit_for(company_id, MONTHLY_AI_TOKEN_CAP)
    after = used_tokens + tokens_in + tokens_out
    allowed = check_ai_allowed(company_id)
    blocked = not allowed.allowed or after > cap
    return {
        "approximate": True,
        "cvs": cvs,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "estimated_cost": f"{Decimal(cost):.6f}",
        "limits": {
            "cvs_this_month": _limit(
                company_id, CVS_PER_MONTH, current["cvs_scored"] + usage.waiting_cvs(company_id)
            ),
            "cvs_in_project": _limit(
                company_id, CVS_PER_PROJECT, CvFile.objects.filter(project=project).count()
            ),
            "tokens": {"used": used_tokens, "limit": cap, "after_estimate": after},
        },
        "blocked": blocked,
        "message": (allowed.message if not allowed.allowed else OVER_CAP_MESSAGE)
        if blocked
        else "",
        "prompt": prompt_kind(company_id) if blocked else None,
    }


def confirm(project, batch_id=None):
    """Releases the held CVs to processing. Refused while the estimate passes the token cap.
    Returns how many were released."""
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=project.company_id)
        require_editable(project)
        shown = estimate(project, batch_id)
        if shown["cvs"] == 0:
            raise AppError(NOTHING_TO_CONFIRM_CODE, NOTHING_TO_CONFIRM_MESSAGE, status_code=409)
        if shown["blocked"]:
            raise AppError(
                OVER_CAP_CODE,
                shown["message"],
                status_code=409,
                details={"prompt": shown["prompt"], "limit": shown["limits"]["tokens"]["limit"]},
            )
        released = _held(project, batch_id).update(
            status=CvFile.Status.WAITING, next_attempt_at=timezone.now()
        )
    kick(released)  # outside the transaction, so workers find the rows
    return released
