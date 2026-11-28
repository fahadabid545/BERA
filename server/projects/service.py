"""Creating a project: the limit check, the warnings and the pinned reading setup."""

from django.db import transaction

from activity import service as activity
from companies.models import Company
from core.errors import AppError
from plans.limits import check_projects
from platform_settings.service import get_setting

from .models import CompanyScoringDefaults, Project, ProjectFactorSettings, ProjectScoringSettings

ARCHIVED_CODE = "project_archived"
UPLOADS_PAUSED_CODE = "uploads_paused"
SCORING_FIELDS = (
    "must_weight_percent",
    "nice_weight_percent",
    "recommendation_threshold",
    "top_n",
    "cap_on_missing_must_have",
)

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


def uploads_block(project):
    """Why no CV may be added to this project now (code and words for the person), or None."""
    if project.uploads_paused:
        return {
            "code": UPLOADS_PAUSED_CODE,
            "message": "Uploads are paused for this project. Resume them in the project settings.",
        }
    return None


def require_uploads_open(project):
    block = uploads_block(project)
    if block:
        raise AppError(block["code"], block["message"], status_code=409)


def set_uploads_paused(actor, project, paused):
    """Pauses or resumes new uploads for a project and logs who did it."""
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project.pk)
        require_editable(project)
        if project.uploads_paused != paused:
            project.uploads_paused = paused
            project.save(update_fields=["uploads_paused", "updated_at"])
            activity.record(
                "setting_changed",
                company_id=project.company_id,
                actor=actor,
                target_kind="project",
                target_id=project.pk,
                details={"setting": "uploads_paused" if paused else "uploads_resumed"},
            )
    return project


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


def create_project(
    creator, title, job_description, *, acknowledge_warnings=False, draft_requirements=True
):
    # Drafting reads the project through `extraction`, which needs this module, so it loads here.
    from .drafting import start_drafting

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
        project = Project.objects.create(
            company=company,
            title=title,
            job_description=job_description,
            reading_model=get_setting("ai.reading_model"),
            scoring_model=get_setting("ai.scoring_model"),
            reading_prompt_version=get_setting("ai.reading_prompt_version"),
            scoring_prompt_version=get_setting("ai.scoring_prompt_version"),
            created_by=creator,
        )
        _start_from_company_defaults(project)
        if draft_requirements:
            start_drafting(project)
        return project


def _start_from_company_defaults(project):
    """Gives the new project its own copy of the company's scoring defaults. The copy is why a
    later change to the defaults leaves this project alone. A company that has saved none gets
    no copy: its project follows the platform's values as before."""
    saved = CompanyScoringDefaults.objects.filter(company_id=project.company_id).first()
    if saved is None:
        return
    ProjectScoringSettings.objects.create(
        project=project,
        company_id=project.company_id,
        **{name: getattr(saved, name) for name in SCORING_FIELDS},
    )
    ProjectFactorSettings.objects.create(
        project=project, company_id=project.company_id, factors=saved.factors
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
