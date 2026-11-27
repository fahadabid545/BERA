"""The company dashboard: one answer per card, all counted from stored data when asked (no AI).

- `dashboard(...)`: the overview numbers (projects, CVs scored, one number for each flag) for the
  chosen period, plus the shares of recommendations and projects and the top candidates.
- `detail(...)`: what is behind a card or a mark in a chart, as a short list the person can open
  from a popup (candidates, CVs, projects or report links, each with the ids the page links to).
- `report(...)`: the same numbers as a plain table, for the CSV file and the printable page.

Candidate names are shown as initials, like everywhere else in the lists.
"""

import csv
import io
from datetime import timedelta
from uuid import UUID

from django.db.models import Avg, Count, Exists, F, OuterRef, Q
from django.http import Http404
from django.utils import timezone

from core.errors import form_error
from core.personal_data import mask_name
from platform_settings.service import get_setting
from projects.models import Project

from . import dashboard_projects
from .charts import GRADES, funnel, percent_change
from .models import Candidate, CandidateScore, CvFile, StageChange

PERCENT = 100
SECONDS_PER_HOUR = 3600
LABELS = ("strong_match", "possible", "not_recommended")
FLAG_STAGES = (
    Candidate.Stage.SHORTLISTED,
    Candidate.Stage.INTERVIEWED,
    Candidate.Stage.ON_HOLD,
    Candidate.Stage.SELECTED,
    Candidate.Stage.REJECTED,
)
PROJECT_STATUSES = ("not_started", "in_progress", "ready")
FUNNEL_STEPS = ("uploaded", "read", "scored", "shortlisted", "interviewed", "selected")
STRENGTHS_SHOWN = 2
# A CSV cell starting with one of these would be run as a formula by a spreadsheet.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def checked_period(raw):
    choices = get_setting("dashboard.period_choices_days")
    try:
        days = get_setting("dashboard.period_default_days") if raw in (None, "") else int(raw)
    except ValueError:
        days = None
    if days not in choices:
        raise form_error({"days": "Choose one of the offered periods."})
    return days


def windows(days):
    """(start, previous_start, end): the last `days` days with today in them, and the same
    number of days before. `end` is the day after today."""
    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    return start, start - timedelta(days=days), today + timedelta(days=1)


def in_days(queryset, column, first, end):
    return queryset.filter(**{f"{column}__date__gte": first, f"{column}__date__lt": end})


def _uploads(company_id, project=None):
    found = CvFile.objects.filter(company_id=company_id).exclude(status=CvFile.Status.CANCELLED)
    return found.filter(project=project) if project else found


def _scores(company_id):
    return CandidateScore.objects.filter(company_id=company_id)


def card(current, previous, series, *, decimals=False):
    change = (
        None
        if previous is None or current is None
        else round(current - previous, 1)
        if decimals
        else percent_change(current, previous)
    )
    return {"value": current, "previous": previous, "change": change, "series": series}


def _recommendations(company_id):
    found = dict(
        _scores(company_id)
        .exclude(candidate__stage=Candidate.Stage.REJECTED)
        .values_list("label")
        .annotate(total=Count("pk"))
    )
    parts = [{"label": label, "count": found.get(label, 0)} for label in LABELS]
    return {"total": sum(part["count"] for part in parts), "parts": parts}


def _project_status_counts(company_id):
    return {status: len(ids) for status, ids in _projects_by_status(company_id).items()}


def _projects_by_status(company_id):
    """The active projects grouped as: nothing uploaded yet, still being worked on, or ready."""
    cvs = CvFile.objects.filter(project=OuterRef("pk")).exclude(status=CvFile.Status.CANCELLED)
    projects = Project.objects.filter(company_id=company_id, status=Project.Status.ACTIVE).annotate(
        has_cvs=Exists(cvs),
        is_busy=Exists(cvs.filter(status__in=CvFile.ACTIVE_STATUSES)),
    )
    grouped = {status: [] for status in PROJECT_STATUSES}
    for project in projects.order_by("-updated_at"):
        key = (
            "not_started" if not project.has_cvs else "in_progress" if project.is_busy else "ready"
        )
        grouped[key].append(project)
    return grouped


def _screening(company_id):
    steps = {item["step"]: item["count"] for item in funnel(company_id)}
    uploaded, scored = steps["uploaded"], steps["scored"]
    return {
        "uploaded": uploaded,
        "scored": scored,
        "percent": round(scored * PERCENT / uploaded, 1) if uploaded else None,
    }


def _candidate_item(candidate, score=None, project=None):
    score = score or getattr(candidate, "score", None)
    project = project or candidate.project
    return {
        "type": "candidate",
        "id": str(candidate.pk),
        "project_id": str(candidate.project_id),
        "project_title": project.title,
        "name": mask_name(candidate.contact.name) if candidate.contact.name else "",
        "file_name": candidate.cv_file.original_name,
        "score": f"{score.score:.1f}" if score else None,
        "grade": score.grade if score else None,
        "label": score.label if score else None,
        "stage": candidate.stage,
    }


def _top_candidates(company_id):
    """The best scored candidates of the whole company (rejected ones left out), each with the
    project they are in, their AI score and their ATS score."""
    ranked = (
        _candidates(company_id)
        .filter(score__isnull=False)
        .exclude(stage=Candidate.Stage.REJECTED)
        .select_related("ats_score")
        .order_by("-score__score", "pk")
    )
    return [
        {
            **_candidate_item(candidate),
            "rank": rank,
            "ats_score": getattr(getattr(candidate, "ats_score", None), "score", None),
        }
        for rank, candidate in enumerate(
            ranked[: get_setting("dashboard.top_candidates_count")], start=1
        )
    ]


def _flagged(company_id, stage, start, end):
    """The candidates now at `stage` that were put there in the period."""
    moved_in = StageChange.objects.filter(
        candidate=OuterRef("pk"),
        to_stage=stage,
        created_at__date__gte=start,
        created_at__date__lt=end,
    )
    return _candidates(company_id).filter(stage=stage).filter(Exists(moved_in))


def _counts(company_id, start, end):
    """The numbers of the overview: every project, the CVs scored in the period and the
    candidates flagged in the period, one number for each flag."""
    counts = {
        "projects": Project.objects.filter(
            company_id=company_id, status=Project.Status.ACTIVE
        ).count(),
        "scored": in_days(_scores(company_id), "created_at", start, end).count(),
    }
    for stage in FLAG_STAGES:
        counts[stage] = _flagged(company_id, stage, start, end).count()
    return counts


def dashboard(company_id, raw_days):
    days = checked_period(raw_days)
    start, _, end = windows(days)
    rows = dashboard_projects.project_rows(company_id)
    return {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "days": days,
        "choices": get_setting("dashboard.period_choices_days"),
        "counts": _counts(company_id, start, end),
        "recommendations": _recommendations(company_id),
        "projects": _project_status_counts(company_id),
        "screening": _screening(company_id),
        "top": _top_candidates(company_id),
        "project_rows": rows,
        "attention": dashboard_projects.attention(rows),
        "uploads_per_day": dashboard_projects.uploads_per_day(company_id, start, days),
        "flag_split": dashboard_projects.flag_split(company_id),
        "missed_requirements": dashboard_projects.missed_requirements(company_id),
    }


# ---- what is behind a card or a mark ----


def _candidates(company_id, project=None):
    found = Candidate.objects.filter(company_id=company_id).select_related(
        "project", "contact", "cv_file", "score"
    )
    return found.filter(project=project) if project else found


def _cv_item(cv):
    return {
        "type": "cv",
        "id": str(cv.pk),
        "project_id": str(cv.project_id),
        "project_title": cv.project.title,
        "file_name": cv.original_name,
        "status": cv.status,
        "at": cv.created_at.isoformat(),
    }


def _project_item(project, **counts):
    return {"type": "project", "id": str(project.pk), "title": project.title, **counts}


def _cvs_of(projects):
    """{project id: {"cvs", "scored", "pending", "failed"}} for the given projects."""
    cvs = CvFile.objects.filter(project__in=projects).exclude(status=CvFile.Status.CANCELLED)
    found = {
        row["project"]: row
        for row in cvs.values("project").annotate(
            cvs=Count("pk"),
            pending=Count("pk", filter=Q(status__in=CvFile.ACTIVE_STATUSES)),
            failed=Count("pk", filter=Q(status=CvFile.Status.FAILED)),
        )
    }
    scored = dict(
        Candidate.objects.filter(project__in=projects, score__isnull=False)
        .values_list("project")
        .annotate(total=Count("pk"))
    )
    return {
        project.pk: {
            "cvs": found.get(project.pk, {}).get("cvs", 0),
            "scored": scored.get(project.pk, 0),
            "pending": found.get(project.pk, {}).get("pending", 0),
            "failed": found.get(project.pk, {}).get("failed", 0),
        }
        for project in projects
    }


def _projects_items(projects):
    counts = _cvs_of(projects)
    return [_project_item(project, **counts[project.pk]) for project in projects]


def _step_items(company_id, step, project=None):
    """Who is behind a funnel step: the CVs for the first step, the candidates after that."""
    if step == "uploaded":
        return _uploads(company_id, project).select_related("project").order_by("-created_at")
    candidates = _candidates(company_id, project)
    if step == "read":
        return candidates.order_by("-created_at")
    scored = candidates.filter(score__isnull=False)
    if step == "scored":
        return scored.order_by("-score__score")
    stages = {
        "shortlisted": (
            Candidate.Stage.SHORTLISTED,
            Candidate.Stage.INTERVIEWED,
            Candidate.Stage.SELECTED,
        ),
        "interviewed": (Candidate.Stage.INTERVIEWED, Candidate.Stage.SELECTED),
        "selected": (Candidate.Stage.SELECTED,),
    }[step]
    reached = Exists(StageChange.objects.filter(candidate=OuterRef("pk"), to_stage__in=stages))
    return scored.filter(Q(stage__in=stages) | reached).order_by("-score__score")


def _items_of(rows):
    return [_cv_item(row) if isinstance(row, CvFile) else _candidate_item(row) for row in rows]


def _project_of(company_id, raw):
    """The company's project named by the request, None when none is named; a project of
    another company, or a bad id, is "not found"."""
    if not raw:
        return None
    try:
        return Project.objects.get(company_id=company_id, pk=UUID(str(raw)))
    except (ValueError, Project.DoesNotExist):
        raise Http404 from None


def detail(company_id, kind, key, raw_days, raw_project=None):
    """{"total", "items"}: what is behind a card, a flag, a funnel step, a grade, a share of
    the donut or a project group. At most `dashboard.detail_limit` items."""
    limit = get_setting("dashboard.detail_limit")
    days = checked_period(raw_days)
    start, _, end = windows(days)
    project = _project_of(company_id, raw_project)
    rows = None
    if kind == "metric" and key == "scored":
        rows = (
            _candidates(company_id)
            .filter(score__created_at__date__gte=start, score__created_at__date__lt=end)
            .order_by("-score__score")
        )
    elif kind == "stage" and key in FLAG_STAGES:
        rows = _flagged(company_id, key, start, end).order_by("-score__score", "-created_at")
    elif kind == "flag" and key in Candidate.Stage.values:
        rows = (
            _candidates(company_id)
            .filter(stage=key)
            .order_by(F("score__score").desc(nulls_last=True), "-created_at")
        )
    elif kind == "funnel" and key in FUNNEL_STEPS:
        rows = _step_items(company_id, key, project)
    elif kind == "grade" and key in GRADES:
        rows = _candidates(company_id, project).filter(score__grade=key).order_by("-score__score")
    elif kind == "recommendation" and key in LABELS:
        rows = (
            _candidates(company_id)
            .filter(score__label=key)
            .exclude(stage=Candidate.Stage.REJECTED)
            .order_by("-score__score")
        )
    elif kind == "project_status" and key in PROJECT_STATUSES:
        projects = _projects_by_status(company_id)[key]
        return {"total": len(projects), "items": _projects_items(projects[:limit])}
    elif kind == "screening":
        projects = list(
            Project.objects.filter(company_id=company_id, status=Project.Status.ACTIVE).order_by(
                "-updated_at"
            )
        )
        return {"total": len(projects), "items": _projects_items(projects[:limit])}
    if rows is None:
        raise form_error({"kind": "Choose something that can be opened."})
    return {"total": rows.count(), "items": _items_of(rows[:limit])}


# ---- the report: the same numbers as a plain table ----


def _project_rows(company_id):
    projects = (
        Project.objects.filter(company_id=company_id, status=Project.Status.ACTIVE)
        .annotate(
            cv_count=Count(
                "cv_files", filter=~Q(cv_files__status=CvFile.Status.CANCELLED), distinct=True
            ),
            scored_count=Count(
                "candidates", filter=Q(candidates__score__isnull=False), distinct=True
            ),
            strong_count=Count(
                "candidates",
                filter=Q(candidates__score__label="strong_match")
                & ~Q(candidates__stage=Candidate.Stage.REJECTED),
                distinct=True,
            ),
            average=Avg("candidates__score__score"),
        )
        .order_by("title")
    )
    return [
        {
            "project": project.title,
            "cvs": project.cv_count,
            "scored": project.scored_count,
            "strong_matches": project.strong_count,
            "average_score": None if project.average is None else round(float(project.average), 1),
        }
        for project in projects
    ]


SUMMARY_LABELS = {
    "projects": "Projects",
    "scored": "CVs scored",
    "shortlisted": "Shortlisted",
    "interviewed": "Interviewed",
    "on_hold": "On hold",
    "selected": "Selected",
    "rejected": "Rejected",
}


def report(company_id, raw_days):
    days = checked_period(raw_days)
    start, _, end = windows(days)
    counts = _counts(company_id, start, end)
    return {
        "days": days,
        "generated_on": timezone.now().date().isoformat(),
        "summary": [
            {"metric": label, "count": counts[name]} for name, label in SUMMARY_LABELS.items()
        ],
        "recommendations": _recommendations(company_id)["parts"],
        "projects": _project_rows(company_id),
    }


def _safe(cell):
    text = "" if cell is None else str(cell)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


def report_csv(data):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["Report for the last", f"{data['days']} days", "Created", data["generated_on"]]
    )
    writer.writerow([])
    writer.writerow(["Metric", "Count"])
    for row in data["summary"]:
        writer.writerow([_safe(row["metric"]), row["count"]])
    writer.writerow([])
    writer.writerow(["Recommendation", "Candidates"])
    for part in data["recommendations"]:
        writer.writerow([_safe(part["label"]), part["count"]])
    writer.writerow([])
    writer.writerow(["Project", "CVs", "Scored", "Strong matches", "Average AI score"])
    for row in data["projects"]:
        writer.writerow(
            [
                _safe(row[key])
                for key in ("project", "cvs", "scored", "strong_matches", "average_score")
            ]
        )
    return out.getvalue()
