"""The company's candidates of every project in one list, for the Candidates page.

One row for each scored-or-not candidate of the company's projects, with the flag (stage) tabs
and filters on top. The tabs are the flags; "all" shows every flag. Filters combine, like the
project list's (`filters.py`), and add the project and what the candidate is missing:
`missing` is `must` (a must-have is judged missing), `nice` (a nice-to-have is) or `none`.
The counts of the tabs follow every filter except the flag itself.
"""

from uuid import UUID

from django.db.models import Count, F, OuterRef, Subquery
from django.http import Http404

from core.errors import form_error
from core.personal_data import mask_name
from platform_settings.service import get_setting
from projects.models import Project, Requirement

from .filters import apply_filters, checked_filters
from .models import Candidate, CvFile, RequirementResult
from .ranking import annotated, checked_query, ordering

ALL = "all"
MISSING_CHOICES = ("must", "nice", "none")
FLAGS = [stage for stage, _ in Candidate.Stage.choices]


def _missing_count(kind):
    return (
        RequirementResult.objects.filter(
            candidate=OuterRef("candidate"),
            verdict=RequirementResult.Verdict.MISSING,
            requirement__kind=kind,
        )
        .values("candidate")
        .annotate(total=Count("pk"))
        .values("total")
    )


def _rows(company_id):
    return annotated(
        CvFile.objects.filter(company_id=company_id, candidate__isnull=False)
    ).annotate(
        missing_must=Subquery(_missing_count(Requirement.Kind.MUST)),
        missing_nice=Subquery(_missing_count(Requirement.Kind.NICE)),
        project_title=F("project__title"),
    )


def _project(company_id, raw):
    try:
        return Project.objects.get(company_id=company_id, pk=UUID(str(raw)))
    except (ValueError, Project.DoesNotExist):
        raise Http404 from None


def _with_missing(rows, choice):
    if choice == "must":
        return rows.filter(missing_must__gt=0)
    if choice == "nice":
        return rows.filter(missing_nice__gt=0)
    return rows.filter(missing_must__isnull=True, missing_nice__isnull=True)


def _row(item):
    scored = item.score_value is not None
    return {
        "id": str(item.candidate_pk),
        "project_id": str(item.project_id),
        "project_title": item.project_title,
        "file_name": item.original_name,
        "name": mask_name(item.contact_name) if item.contact_name else "",
        "score": f"{item.score_value:.1f}" if scored else None,
        "grade": item.grade_value,
        "ats_score": item.ats_value,
        "label": item.label_value,
        "stage": item.stage_value,
        "missing_must": item.missing_must or 0,
        "missing_nice": item.missing_nice or 0,
        "added_at": item.created_at.isoformat(),
    }


def candidates_page(company_id, params):
    """One page of the company's candidates for the chosen flag and filters, the number behind
    each flag tab and the projects to filter by."""
    sort, direction, page = checked_query(params)
    flag = params.get("flag") or ALL
    missing = params.get("missing") or ""
    problems = {}
    if flag != ALL and flag not in FLAGS:
        problems["flag"] = "Choose one of the flags."
    if missing and missing not in MISSING_CHOICES:
        problems["missing"] = "Choose must-have, nice-to-have or nothing missing."
    if problems:
        raise form_error(problems)
    # The project-only filters are checked by the list's own checks, with no project named.
    filters = checked_filters(
        {key: value for key, value in params.items() if key not in ("stage", "missing", "has")},
        None,
    )
    rows = apply_filters(_rows(company_id), filters)
    if params.get("project"):
        rows = rows.filter(project=_project(company_id, params["project"]))
    if missing:
        rows = _with_missing(rows, missing)
    counts = dict(rows.order_by().values_list("stage_value").annotate(total=Count("pk")).order_by())
    size = get_setting("candidates.page_size")
    shown = rows if flag == ALL else rows.filter(stage_value=flag)
    total = shown.count()
    pages = max(1, -(-total // size))
    page = min(page, pages)
    window = shown.order_by(*ordering(sort, direction))[(page - 1) * size : page * size]
    return {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "flag": flag,
        "sort": sort,
        "direction": direction,
        "page": page,
        "pages": pages,
        "count": total,
        "flags": {ALL: sum(counts.values()), **{name: counts.get(name, 0) for name in FLAGS}},
        "projects": [
            {"id": str(project.pk), "title": project.title}
            for project in Project.objects.filter(
                company_id=company_id, status=Project.Status.ACTIVE
            ).order_by("title")
        ],
        "rows": [_row(item) for item in window],
    }
