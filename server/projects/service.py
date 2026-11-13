"""Creating a project: the limit check, the warnings and the pinned reading setup."""

from django.db import transaction

from companies.models import Company
from core.errors import AppError
from plans.limits import check_projects
from platform_settings.service import get_setting

from .models import Project

SHORT_DESCRIPTION = "short_description"
DUPLICATE_TITLE = "duplicate_title"
WARNINGS_CODE = "project_warnings"


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
        projects_now = Project.objects.filter(company=company).count()
        check_projects(company.pk, projects_now).raise_if_blocked()
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
            prompt_version=get_setting("ai.prompt_version"),
            created_by=creator,
        )
