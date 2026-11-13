"""The company's projects as a page: search, filter, sort and paging."""

from django.db.models import FloatField, IntegerField, Value
from django.db.models.functions import Lower

from platform_settings.service import get_setting

from .models import Project

SORTS = {
    "updated": ("-updated_at", "-id"),
    "title": (Lower("title").asc(), "-updated_at", "-id"),
    # Projects without a score sort last; the score comes with the Candidate record ticket.
    "best_score": ("-best_score", "-updated_at", "-id"),
}
STATUS_FILTERS = ("active", "archived", "all")
DEFAULT_SORT = "updated"
DEFAULT_STATUS = "active"


def with_figures(projects):
    """CV count and best score per project. Zero and empty until candidates exist: this is the
    one place to change when they do."""
    return projects.annotate(
        cv_count=Value(0, output_field=IntegerField()),
        best_score=Value(None, output_field=FloatField()),
    )


def list_projects(company_id, *, search="", status=DEFAULT_STATUS, sort=DEFAULT_SORT, page=1):
    projects = Project.objects.filter(company_id=company_id)
    if status != "all":
        projects = projects.filter(status=status)
    if search:
        projects = projects.filter(title__icontains=search)
    projects = with_figures(projects).order_by(*SORTS[sort])

    size = get_setting("projects.page_size")
    total = projects.count()
    first = (page - 1) * size
    return {
        "results": [describe(project) for project in projects[first : first + size]],
        "page": page,
        "page_size": size,
        "total": total,
        "pages": max(1, -(-total // size)),
    }


def describe(project):
    return {
        "id": str(project.id),
        "title": project.title,
        "cv_count": project.cv_count,
        "best_score": project.best_score,
        "status": project.status,
        "updated_at": project.updated_at.isoformat(),
    }
