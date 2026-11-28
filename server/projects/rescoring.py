"""What changing a project's requirements means for the CVs already scored: the estimate shown
before saving, and starting the re-scoring after it. The work itself is in `cvs/rescoring.py`
(cvs builds on projects, so it is imported when used)."""

from django.db import transaction

from core.errors import AppError

from .models import Project, Requirement
from .service import require_editable

RESCORING_CODE = "rescoring_needed"
REQUIREMENTS_CHANGED = "Re-scoring needed: changing the requirements means scoring the CVs again."
EVERYTHING = "Scoring everything again means judging every CV against every requirement again."
NOTHING_TO_SCORE_CODE = "nothing_to_rescore"


def require_acknowledged(rescoring, acknowledged, message):
    """Stops a change that needs AI work when the AI is not allowed, or when the person has not
    yet seen how many CVs will run and what it may cost."""
    if rescoring["blocked"]:
        raise AppError(
            rescoring["code"], rescoring["message"], status_code=409,
            details={"prompt": rescoring["prompt"]},
        )  # fmt: skip
    if rescoring["cvs"] > 0 and not acknowledged:
        raise AppError(
            RESCORING_CODE,
            message,
            status_code=409,
            details={
                "cvs": rescoring["cvs"],
                "requirements": rescoring["requirements"],
                "estimated_cost": f"{rescoring['estimated_cost']:.6f}",
            },
        )


def rescore_everything(project_id, company_id, acknowledged):
    """Judges every scored CV against every requirement again. Asks first (the CV count and the
    approximate cost come back as a refusal until acknowledged). Returns the CVs queued."""
    from cvs.rescoring import estimate, mark_everything_stale, start

    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        require_editable(project)
        items = [
            {"id": str(item.pk), "text": item.text}
            for item in Requirement.objects.filter(project=project)
        ]
        rescoring = estimate(project, items, everything=True)
        if rescoring["cvs"] == 0:
            raise AppError(
                NOTHING_TO_SCORE_CODE,
                "There are no scored CVs to score again.",
                status_code=409,
            )
        require_acknowledged(rescoring, acknowledged, EVERYTHING)
        mark_everything_stale(project)
        queued = start(project)
    wake_workers(queued)
    return queued


def changed_requirement_count(project, items):
    """How many requirements of the new list are new or have new wording (the only ones that
    need the AI; weights, kinds and order never do)."""
    from cvs.rescoring import changed_texts

    return changed_texts(project, items)


def rescoring_estimate(project, items):
    """The CVs that would run again, the approximate cost, and whether the plan's AI allowance
    would be passed."""
    from cvs.rescoring import estimate

    return estimate(project, items)


def start_rescoring(project):
    """Marks the scored candidates Outdated and queues their CVs; returns how many were queued."""
    from cvs.rescoring import start

    return start(project)


def wake_workers(queued):
    from cvs.rescoring import wake

    wake(queued)
