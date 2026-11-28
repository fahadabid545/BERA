"""A project's requirements: add, edit, remove and reorder, saved as one list.

The whole list is sent and replaces the stored one, so order, weights and removals can never
disagree. Requirements are never scored here; they only have to be right before scoring."""

import re
from difflib import SequenceMatcher

from django.db import transaction

from core.errors import AppError, form_error
from cvs.models import CvFile
from platform_settings.service import get_setting

from .deletion import register_project_data
from .models import Project, Requirement
from .recalculation import recalculate_scores
from .rescoring import (
    REQUIREMENTS_CHANGED,
    changed_requirement_count,
    require_acknowledged,
    rescoring_estimate,
    start_rescoring,
    wake_workers,
)
from .service import require_editable

NEEDED_CODE = "requirements_needed"
NEAR_DUPLICATE = "near_duplicate"
NOT_A_DRAFT_CODE = "requirements_not_a_draft"


def list_requirements(project):
    return [
        {"id": str(item.id), "kind": item.kind, "text": item.text, "weight": item.weight}
        for item in Requirement.objects.filter(project=project).order_by("position", "created_at")
    ]


def _words(text):
    return " ".join(re.findall(r"\w+", text.lower()))


def near_duplicates(items):
    """Pairs of requirements whose wording is (nearly) the same, in the order given."""
    threshold = get_setting("requirements.near_duplicate_percent") / 100
    pairs = []
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            a, b = _words(first["text"]), _words(second["text"])
            if a == b or SequenceMatcher(None, a, b).ratio() >= threshold:
                pairs.append(
                    {
                        "code": NEAR_DUPLICATE,
                        "message": f'"{first["text"]}" and "{second["text"]}" look alike.',
                        "texts": [first["text"], second["text"]],
                    }
                )
    return pairs


def _checked(items):
    limit = get_setting("requirements.max_total")
    if len(items) > limit:
        raise form_error({"requirements": f"A project can have at most {limit} requirements."})
    default_weight = get_setting("requirements.weight_default")
    return [{**item, "weight": item.get("weight") or default_weight} for item in items]


def save_requirements(project_id, company_id, items, *, acknowledge_rescoring=False):
    """Replaces the project's requirements with `items` (dicts of kind, text, weight and, for
    an existing one, id). Returns the stored list and the near-duplicate warnings."""
    items = _checked(items)
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        require_editable(project)
        stored = {str(item.id): item for item in Requirement.objects.filter(project=project)}
        unknown = [item["id"] for item in items if item.get("id") and item["id"] not in stored]
        if unknown:
            raise form_error({"requirements": "One of these requirements no longer exists."})
        rescoring = None
        if changed_requirement_count(project, items):
            rescoring = rescoring_estimate(project, items)
            require_acknowledged(rescoring, acknowledge_rescoring, REQUIREMENTS_CHANGED)
        kept = set()
        for position, item in enumerate(items):
            fields = {
                "position": position,
                "kind": item["kind"],
                "text": item["text"],
                "weight": item["weight"],
            }
            if item.get("id"):
                Requirement.objects.filter(pk=item["id"]).update(**fields)
                kept.add(item["id"])
            else:
                created = Requirement.objects.create(
                    company_id=company_id, project=project, **fields
                )
                kept.add(str(created.id))
        Requirement.objects.filter(project=project).exclude(pk__in=kept).delete()
        released = _confirm(project)
        recalculate_scores(project)
        queued = start_rescoring(project) if rescoring and rescoring["cvs"] > 0 else 0
    wake_workers(queued + released)  # outside the transaction, so workers find the rows
    return list_requirements(project), near_duplicates(items)


def _confirm(project):
    """Marks the list as checked by the person and saves the project. Returns how many CVs were
    waiting for this, so the caller can wake the workers."""
    held = project.requirements_status != Project.RequirementsStatus.CONFIRMED
    project.requirements_status = Project.RequirementsStatus.CONFIRMED
    project.requirements_notice = ""
    project.save(update_fields=["requirements_status", "requirements_notice", "updated_at"])
    return (
        CvFile.objects.filter(project=project, status=CvFile.Status.WAITING).count() if held else 0
    )


def confirm_requirements(project_id, company_id):
    """The person accepts the drafted list as it is. Needs at least one requirement."""
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        require_editable(project)
        require_requirements_for_scoring(project)
        released = _confirm(project)
    wake_workers(released)
    return list_requirements(project)


def start_rereading(project_id, company_id):
    """Asks the AI to draft the list again. Only while the list is still a draft: once it is
    confirmed, CVs have been scored against it and changing it goes through re-scoring."""
    from .drafting import start_drafting

    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        require_editable(project)
        if project.requirements_status != Project.RequirementsStatus.DRAFT:
            raise AppError(
                NOT_A_DRAFT_CODE,
                "The job description can only be read again before the requirements are confirmed.",
                status_code=409,
            )
        start_drafting(project)


def require_requirements_for_scoring(project):
    """Scoring must not start with nothing to score against; the scoring tickets call this."""
    if not Requirement.objects.filter(project=project).exists():
        raise AppError(
            NEEDED_CODE,
            "Add at least one requirement before scoring starts.",
            status_code=409,
        )


def _remove_for_project(company_id, project_id):
    Requirement.objects.filter(company_id=company_id, project_id=project_id).delete()


register_project_data("Requirement", _remove_for_project)
