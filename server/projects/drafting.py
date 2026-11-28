"""Drafting a new project's requirements from its job description, in the background.

The project is created at once with its requirements `drafting`; a worker asks the AI and stores
the answer as the first list, marking it `draft`. Nothing is scored until the person checks the
list and confirms it (see `requirements.confirm_requirements`). An AI that is unavailable, paused
or blocked by the plan leaves an empty draft with a plain notice, so the person can type the
list themselves.
"""

from django.db import transaction
from django_q.tasks import async_task

from core.errors import AppError
from core.jobs import logged_job

from .extraction import FALLBACK_MESSAGE, suggest_requirements
from .models import Project, Requirement

DRAFT_JOB = "projects.drafting.draft_requirements"


def start_drafting(project):
    """Marks the project as being read and queues the job once its creation is saved."""
    Project.objects.filter(pk=project.pk).update(
        requirements_status=Project.RequirementsStatus.DRAFTING, requirements_notice=""
    )
    project.requirements_status = Project.RequirementsStatus.DRAFTING
    transaction.on_commit(lambda: async_task(DRAFT_JOB, str(project.pk)))


def _notice(suggestion):
    if suggestion["fallback"]:
        return suggestion["message"]
    return " ".join(warning["message"] for warning in suggestion["warnings"])


def _store_draft(project_id, requirements, notice):
    """Saves the draft unless the person got there first (saved or confirmed their own list,
    or asked for another reading) while the AI was working."""
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id)
        if project.requirements_status != Project.RequirementsStatus.DRAFTING:
            return
        Requirement.objects.filter(project=project).delete()
        Requirement.objects.bulk_create(
            Requirement(
                company_id=project.company_id,
                project=project,
                position=position,
                kind=item["kind"],
                text=item["text"],
                weight=item["weight"],
            )
            for position, item in enumerate(requirements)
        )
        project.requirements_status = Project.RequirementsStatus.DRAFT
        project.requirements_notice = notice
        project.save(update_fields=["requirements_status", "requirements_notice"])


@logged_job
def draft_requirements(project_id):
    """Background job: asks the AI for the project's requirements and stores them as a draft.
    A repeated job finds the project no longer drafting and does nothing."""
    project = Project.objects.filter(
        pk=project_id, requirements_status=Project.RequirementsStatus.DRAFTING
    ).first()
    if project is None:
        return
    try:
        suggestion = suggest_requirements(project)
    except AppError as blocked:  # the plan or an admin pause does not allow the AI right now
        _store_draft(project_id, [], blocked.message)
        return
    except Exception:
        # Leave the person with an empty list they can fill in, then let the job log the cause.
        _store_draft(project_id, [], FALLBACK_MESSAGE)
        raise
    _store_draft(project_id, suggestion["requirements"], _notice(suggestion))
