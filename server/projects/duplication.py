"""Duplicating a project: the same job description, requirements, scoring settings and factors,
and no CVs. The copy counts as a new project for the plan's project limit. Its requirements are
already checked, so it is confirmed at once and the AI is not asked again."""

from django.db import transaction

from platform_settings.service import get_setting

from .models import Project, ProjectFactorSettings, ProjectScoringSettings, Requirement
from .service import create_project

COPY_SUFFIX = " (copy)"
NOT_COPIED = {"id", "project", "company", "created_at", "updated_at"}


def _copy_title(title):
    room = get_setting("projects.title_max_length") - len(COPY_SUFFIX)
    return title[:room].rstrip() + COPY_SUFFIX


def _copy_of(row, project):
    """A new row for `project` with every value of `row` except its identity and dates."""
    values = {
        field.attname: getattr(row, field.attname)
        for field in row._meta.concrete_fields
        if field.name not in NOT_COPIED
    }
    return type(row)(project=project, company_id=project.company_id, **values)


def duplicate_project(creator, source):
    with transaction.atomic():
        project = create_project(
            creator,
            _copy_title(source.title),
            source.job_description,
            acknowledge_warnings=True,  # a repeated title is the point of a copy
            draft_requirements=False,
        )
        Requirement.objects.bulk_create(
            _copy_of(requirement, project)
            for requirement in Requirement.objects.filter(project=source).order_by("position")
        )
        for model in (ProjectScoringSettings, ProjectFactorSettings):
            row = model.objects.filter(project=source).first()
            if row is not None:
                # The new project may already hold the company's defaults; the source wins.
                model.objects.filter(project=project).delete()
                _copy_of(row, project).save()
        Project.objects.filter(pk=project.pk).update(
            labels=source.labels,
            requirements_status=source.requirements_status
            if source.requirements_status != Project.RequirementsStatus.DRAFTING
            else Project.RequirementsStatus.DRAFT,
        )
    return project
