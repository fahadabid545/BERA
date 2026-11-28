"""The company's projects as a page: search, filter, sort and paging."""

from django.db.models import Count, F, Max
from django.db.models.functions import Lower

from plans.limits import CVS_PER_PROJECT, limit_for
from platform_settings.service import get_setting

from .models import Project

SORTS = {
    "updated": ("-updated_at", "-id"),
    "title": (Lower("title").asc(), "-updated_at", "-id"),
    # Projects without a score sort last.
    "best_score": (F("best_score").desc(nulls_last=True), "-updated_at", "-id"),
}
STATUS_FILTERS = ("active", "archived", "all")
DEFAULT_SORT = "updated"
DEFAULT_STATUS = "active"


def with_figures(projects):
    """CV count and best score per project. The count is every CV of the project, the same
    number the per-project limit checks."""
    return projects.annotate(
        cv_count=Count("cv_files", distinct=True),
        best_score=Max("candidates__score__score"),
    ).select_related("created_by")


def company_labels(company_id):
    """Every label in use in the company, for choosing and filtering."""
    lists = Project.objects.filter(company_id=company_id).values_list("labels", flat=True)
    return sorted({label for labels in lists for label in labels}, key=str.casefold)


def list_projects(
    company_id, *, search="", status=DEFAULT_STATUS, sort=DEFAULT_SORT, label="", page=1
):
    projects = Project.objects.filter(company_id=company_id)
    if status != "all":
        projects = projects.filter(status=status)
    if search:
        projects = projects.filter(title__icontains=search)
    if label:
        projects = projects.filter(labels__contains=[label])
    projects = with_figures(projects).order_by(*SORTS[sort])

    size = get_setting("projects.page_size")
    total = projects.count()
    first = (page - 1) * size
    capacity = limit_for(company_id, CVS_PER_PROJECT)
    return {
        "results": [describe(project, capacity) for project in projects[first : first + size]],
        "page": page,
        "page_size": size,
        "total": total,
        "pages": max(1, -(-total // size)),
        "labels": company_labels(company_id),
    }


def describe(project, capacity):
    """One project card: who made it, when, and how many CVs it holds out of how many it can."""
    return {
        "id": str(project.id),
        "title": project.title,
        "created_by": project.created_by.name,
        "created_at": project.created_at.isoformat(),
        "cv_count": project.cv_count,
        "cv_capacity": capacity,
        "best_score": None if project.best_score is None else float(project.best_score),
        "status": project.status,
        "labels": project.labels,
        "updated_at": project.updated_at.isoformat(),
    }
