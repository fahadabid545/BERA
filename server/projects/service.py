"""Creating a project: the limit check, the warnings and the pinned reading setup."""

from django.db import transaction

from companies.models import Company
from core.errors import AppError
from plans.limits import check_projects
from platform_settings.service import get_setting

from .models import Project

ARCHIVED_CODE = "project_archived"

SHORT_DESCRIPTION = "short_description"
DUPLICATE_TITLE = "duplicate_title"
WARNINGS_CODE = "project_warnings"


def active_project_count(company_id):
    """Archived projects do not count toward the plan's project limit."""
    return Project.objects.filter(company_id=company_id, status=Project.Status.ACTIVE).count()


def require_editable(project):
    """An archived project is read-only. Later tickets (uploads, edits) call this first;
    downloads do not."""
    if project.status == Project.Status.ARCHIVED:
        raise AppError(
            ARCHIVED_CODE,
            "This project is archived. Restore it to make changes.",
            status_code=409,
        )


def warnings_for(company_id, title, job_description):
    """Things worth a second look that do not stop the project from being created."""
    found = []
    minimum = get_setting("projects.short_description_length")
    if len(job_description) < minimum:
        found.append(
            {
                "code": SHORT_DESCRIPTION,
                "message": f"This description is under {minimum} characters, so scoring "
                "quality will be poor.",
            }
        )
    if Project.objects.filter(company_id=company_id, title__iexact=title).exists():
        found.append(
            {
                "code": DUPLICATE_TITLE,
                "message": "You already have a project with this title.",
            }
        )
    return found


def create_project(creator, title, job_description, *, acknowledge_warnings=False):
    with transaction.atomic():
        # The company row lock makes two creations at once see each other's project, so they
        # cannot pass the plan limit together.
        company = Company.objects.select_for_update().get(pk=creator.company_id)
        check_projects(company.pk, active_project_count(company.pk)).raise_if_blocked()
        warnings = warnings_for(company.pk, title, job_description)
        if warnings and not acknowledge_warnings:
            raise AppError(
                WARNINGS_CODE,
                "Please check the warnings before creating this project.",
                status_code=409,
                details={"warnings": warnings},
            )
        return Project.objects.create(
            company=company,
            title=title,
            job_description=job_description,
            reading_model=get_setting("ai.reading_model"),
            scoring_model=get_setting("ai.scoring_model"),
            reading_prompt_version=get_setting("ai.reading_prompt_version"),
            scoring_prompt_version=get_setting("ai.scoring_prompt_version"),
            created_by=creator,
        )


def update_project(project_id, company_id, *, title=None, job_description=None):
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        require_editable(project)
        if title is not None:
            project.title = title
        if job_description is not None:
            project.job_description = job_description
        project.save()
        return project


def archive_project(project_id, company_id):
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        if project.status == Project.Status.ARCHIVED:
            raise AppError(ARCHIVED_CODE, "This project is already archived.", status_code=409)
        project.status = Project.Status.ARCHIVED
        project.save()
        return project


def restore_project(project_id, company_id):
    """Back to active. It counts toward the project limit again, so it can be refused."""
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=company_id)
        project = Project.objects.select_for_update().get(pk=project_id, company_id=company_id)
        if project.status == Project.Status.ACTIVE:
            raise AppError("project_not_archived", "This project is not archived.", status_code=409)
        check_projects(company_id, active_project_count(company_id)).raise_if_blocked()
        project.status = Project.Status.ACTIVE
        project.save()
        return project
