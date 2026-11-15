"""The company dashboard: one answer per card, all counted from stored data when asked (no AI).

- `dashboard(...)`: the cards. Numbers for the chosen period sit next to the period before it
  (same length), so every figure says whether it is more or less than before.
- `detail(...)`: what is behind a card or a mark in a chart, as a short list the person can open
  from a popup (candidates, CVs, projects or report links, each with the ids the page links to).
- `report(...)`: the same numbers as a plain table, for the CSV file and the printable page.

Candidate names are shown as initials, like everywhere else in the lists.
"""

import csv
import io
import statistics
from datetime import timedelta
from uuid import UUID

from django.db.models import Avg, Count, Exists, Min, OuterRef, Q
from django.db.models.functions import TruncDate
from django.http import Http404
from django.utils import timezone

from core.errors import form_error
from core.personal_data import mask_name
from platform_settings.service import get_setting
from projects.models import Project

from .charts import GRADES, funnel, per_day, percent_change
from .models import Candidate, CandidateScore, CvFile, SharedReport, StageChange
from .top_list import top_scores

PERCENT = 100
SECONDS_PER_HOUR = 3600
LABELS = ("strong_match", "possible", "not_recommended")
SHORTLISTED_STAGES = (Candidate.Stage.SHORTLISTED,)
PROJECT_STATUSES = ("not_started", "in_progress", "ready")
FUNNEL_STEPS = ("uploaded", "read", "scored", "shortlisted", "interview", "approved")
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


def _windows(days):
    """(start, previous_start, end): the last `days` days with today in them, and the same
    number of days before. `end` is the day after today."""
    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    return start, start - timedelta(days=days), today + timedelta(days=1)


def _in_days(queryset, column, first, end):
    return queryset.filter(**{f"{column}__date__gte": first, f"{column}__date__lt": end})


def _uploads(company_id, project=None):
    found = CvFile.objects.filter(company_id=company_id).exclude(status=CvFile.Status.CANCELLED)
    return found.filter(project=project) if project else found


def _scores(company_id):
    return CandidateScore.objects.filter(company_id=company_id)


def _shortlist_changes(company_id):
    return StageChange.objects.filter(company_id=company_id, to_stage__in=SHORTLISTED_STAGES)


def _shortlisted_ids(company_id, first, end):
    """The candidates first moved to Shortlisted in the period (one moved there twice counts
    once, on the first day)."""
    firsts = _shortlist_changes(company_id).values("candidate").annotate(first=Min("created_at"))
    return [row["candidate"] for row in firsts if first <= row["first"].date() < end]


def _filled(values):
    """A list of daily averages where an empty day repeats the day before, so a line is drawn
    through quiet days instead of dropping to zero."""
    known = next((value for value in values if value is not None), 0)
    filled = []
    for value in values:
        known = known if value is None else value
        filled.append(known)
    return filled


def _daily_average(company_id, first, days):
    found = dict(
        _in_days(_scores(company_id), "created_at", first, first + timedelta(days=days))
        .annotate(day=TruncDate("created_at"))
        .values_list("day")
        .annotate(mean=Avg("score"))
    )
    return _filled(
        [
            float(found[first + timedelta(days=offset)])
            if first + timedelta(days=offset) in found
            else None
            for offset in range(days)
        ]
    )


def _card(current, previous, series, *, decimals=False):
    change = (
        None
        if previous is None or current is None
        else round(current - previous, 1)
        if decimals
        else percent_change(current, previous)
    )
    return {"value": current, "previous": previous, "change": change, "series": series}


def _average(queryset):
    mean = queryset.aggregate(mean=Avg("score"))["mean"]
    return None if mean is None else round(float(mean), 1)


def _cards(company_id, start, before, end):
    spark = get_setting("dashboard.sparkline_days")
    spark_start = timezone.now().date() - timedelta(days=spark - 1)
    uploads, scores = _uploads(company_id), _scores(company_id)
    shortlist = _shortlist_changes(company_id)
    shortlist_days = [
        len(
            {
                row["candidate"]
                for row in shortlist.filter(
                    created_at__date=spark_start + timedelta(days=i)
                ).values("candidate")
            }
        )
        for i in range(spark)
    ]
    return {
        "uploaded": _card(
            _in_days(uploads, "created_at", start, end).count(),
            _in_days(uploads, "created_at", before, start).count(),
            per_day(uploads, "created_at", spark_start, spark),
        ),
        "scored": _card(
            _in_days(scores, "created_at", start, end).count(),
            _in_days(scores, "created_at", before, start).count(),
            per_day(scores, "created_at", spark_start, spark),
        ),
        "shortlisted": _card(
            len(_shortlisted_ids(company_id, start, end)),
            len(_shortlisted_ids(company_id, before, start)),
            shortlist_days,
        ),
        "average_score": _card(
            _average(_in_days(scores, "created_at", start, end)),
            _average(_in_days(scores, "created_at", before, start)),
            _daily_average(company_id, spark_start, spark),
            decimals=True,
        ),
    }


def _strong_share(company_id, first, end):
    scored = _in_days(_scores(company_id), "created_at", first, end)
    total = scored.count()
    if not total:
        return None
    return round(scored.filter(label="strong_match").count() * PERCENT / total, 1)


def _hours_to_shortlist(company_id, first, end):
    """The median hours from a candidate being added to being shortlisted, for those
    shortlisted in the period; None when nobody was."""
    rows = (
        _shortlist_changes(company_id)
        .values("candidate", "candidate__created_at")
        .annotate(first=Min("created_at"))
    )
    waits = [
        (row["first"] - row["candidate__created_at"]).total_seconds() / SECONDS_PER_HOUR
        for row in rows
        if first <= row["first"].date() < end
    ]
    return round(statistics.median(waits), 1) if waits else None


def _insights(company_id, start, before, end, cards):
    uploaded = cards["uploaded"]
    share, share_before = (
        _strong_share(company_id, start, end),
        _strong_share(company_id, before, start),
    )
    return {
        "hiring_pace": {
            "current": uploaded["value"],
            "previous": uploaded["previous"],
            "change": uploaded["change"],
        },
        "match_quality": {
            "share": share,
            "previous_share": share_before,
            "change": None
            if share is None or share_before is None
            else round(share - share_before, 1),
        },
        "time_to_shortlist": {
            "hours": _hours_to_shortlist(company_id, start, end),
            "previous_hours": _hours_to_shortlist(company_id, before, start),
        },
    }


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


def _pending(company_id):
    cvs = _uploads(company_id)
    now = timezone.now()
    expiring = SharedReport.objects.filter(
        company_id=company_id,
        revoked_at__isnull=True,
        expires_at__gt=now,
        expires_at__lte=now + timedelta(days=get_setting("dashboard.expiring_link_days")),
    )
    return {
        "awaiting_confirmation": cvs.filter(status=CvFile.Status.AWAITING_CONFIRMATION).count(),
        "failed": cvs.filter(status=CvFile.Status.FAILED).count(),
        "links_expiring": expiring.count(),
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


def _top_candidates(company_id, raw_project):
    projects = list(
        Project.objects.filter(company_id=company_id, status=Project.Status.ACTIVE).order_by(
            "-updated_at"
        )
    )
    chosen = None
    if raw_project:
        try:
            chosen = next((p for p in projects if p.pk == UUID(str(raw_project))), None)
        except ValueError:
            chosen = None
        if chosen is None:
            raise Http404
    else:
        scored = set(_scores(company_id).values_list("candidate__project_id", flat=True).distinct())
        chosen = next((p for p in projects if p.pk in scored), None)
    cards = []
    for item in (
        top_scores(chosen)[: get_setting("dashboard.top_candidates_count")] if chosen else []
    ):
        candidate = item.candidate
        cards.append(
            {
                **_candidate_item(candidate, item, chosen),
                "rank": len(cards) + 1,
                "strengths": list(item.strengths)[:STRENGTHS_SHOWN],
                "ats_score": getattr(getattr(candidate, "ats_score", None), "score", None),
            }
        )
    return {
        "projects": [{"id": str(p.pk), "title": p.title} for p in projects],
        "project_id": str(chosen.pk) if chosen else None,
        "candidates": cards,
        "compare_limits": {
            "min": get_setting("comparison.min_candidates"),
            "max": get_setting("comparison.max_candidates"),
        },
    }


def _activity(company_id):
    limit = get_setting("dashboard.activity_limit")
    events = []
    scored = _scores(company_id).select_related(
        "candidate__contact", "candidate__project", "candidate__cv_file"
    )
    for item in scored.order_by("-created_at")[:limit]:
        events.append(
            {**_candidate_item(item.candidate, item), "kind": "scored", "at": item.created_at}
        )
    moved = StageChange.objects.filter(company_id=company_id).select_related(
        "candidate__contact", "candidate__project", "candidate__cv_file", "candidate__score"
    )
    for change in moved.order_by("-created_at")[:limit]:
        events.append(
            {
                **_candidate_item(change.candidate),
                "kind": "moved",
                "to_stage": change.to_stage,
                "at": change.created_at,
            }
        )
    shared = SharedReport.objects.filter(company_id=company_id).select_related("project")
    for report_row in shared.order_by("-created_at")[:limit]:
        events.append(
            {
                "type": "report",
                "kind": "shared",
                "id": str(report_row.pk),
                "project_id": str(report_row.project_id),
                "project_title": report_row.project_title,
                "views": report_row.views,
                "at": report_row.created_at,
            }
        )
    events.sort(key=lambda event: event["at"], reverse=True)
    return [{**event, "at": event["at"].isoformat()} for event in events[:limit]]


def dashboard(company_id, raw_days, raw_project=None):
    days = checked_period(raw_days)
    start, before, end = _windows(days)
    cards = _cards(company_id, start, before, end)
    return {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "days": days,
        "choices": get_setting("dashboard.period_choices_days"),
        "cards": cards,
        "insights": _insights(company_id, start, before, end, cards),
        "recommendations": _recommendations(company_id),
        "projects": _project_status_counts(company_id),
        "screening": _screening(company_id),
        "top": _top_candidates(company_id, raw_project),
        "pending": _pending(company_id),
        "activity": _activity(company_id),
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


def _shortlisted_candidates(company_id, first, end):
    return _candidates(company_id).filter(pk__in=_shortlisted_ids(company_id, first, end))


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
            Candidate.Stage.INTERVIEW,
            Candidate.Stage.APPROVED,
        ),
        "interview": (Candidate.Stage.INTERVIEW, Candidate.Stage.APPROVED),
        "approved": (Candidate.Stage.APPROVED,),
    }[step]
    reached = Exists(StageChange.objects.filter(candidate=OuterRef("pk"), to_stage__in=stages))
    return scored.filter(Q(stage__in=stages) | reached).order_by("-score__score")


def _items_of(rows):
    return [_cv_item(row) if isinstance(row, CvFile) else _candidate_item(row) for row in rows]


def _metric_rows(company_id, key, start, end):
    if key == "uploaded":
        return (
            _in_days(_uploads(company_id), "created_at", start, end)
            .select_related("project")
            .order_by("-created_at")
        )
    if key == "scored":
        return (
            _candidates(company_id)
            .filter(score__created_at__date__gte=start, score__created_at__date__lt=end)
            .order_by("-score__score")
        )
    if key == "shortlisted":
        return _shortlisted_candidates(company_id, start, end).order_by("-score__score")
    if key == "average_score":
        return _metric_rows(company_id, "scored", start, end)
    return None


def _pending_rows(company_id, key):
    if key == "links_expiring":
        now = timezone.now()
        return SharedReport.objects.filter(
            company_id=company_id,
            revoked_at__isnull=True,
            expires_at__gt=now,
            expires_at__lte=now + timedelta(days=get_setting("dashboard.expiring_link_days")),
        ).order_by("expires_at")
    status = {
        "awaiting_confirmation": CvFile.Status.AWAITING_CONFIRMATION,
        "failed": CvFile.Status.FAILED,
    }.get(key)
    if status is None:
        return None
    return (
        _uploads(company_id).filter(status=status).select_related("project").order_by("-created_at")
    )


def _report_item(row):
    return {
        "type": "report",
        "id": str(row.pk),
        "project_id": str(row.project_id),
        "project_title": row.project_title,
        "expires_at": row.expires_at.isoformat(),
        "views": row.views,
    }


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
    """{"total", "items"}: what is behind a card, an insight, a funnel step, a grade, a share of
    the donut, a project group or a pending item. At most `dashboard.detail_limit` items."""
    limit = get_setting("dashboard.detail_limit")
    days = checked_period(raw_days)
    start, _, end = _windows(days)
    project = _project_of(company_id, raw_project)
    rows = None
    if kind in ("metric", "insight"):
        mapped = {
            "hiring_pace": "uploaded",
            "match_quality": "scored",
            "time_to_shortlist": "shortlisted",
        }
        rows = _metric_rows(company_id, mapped.get(key, key), start, end)
        if kind == "insight" and key == "match_quality" and rows is not None:
            rows = rows.filter(score__label="strong_match")
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
    elif kind == "pending":
        rows = _pending_rows(company_id, key)
        if rows is not None and key == "links_expiring":
            return {"total": rows.count(), "items": [_report_item(row) for row in rows[:limit]]}
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


def report(company_id, raw_days):
    days = checked_period(raw_days)
    start, before, end = _windows(days)
    cards = _cards(company_id, start, before, end)
    labels = {
        "uploaded": "CVs uploaded",
        "scored": "CVs scored",
        "shortlisted": "Candidates shortlisted",
        "average_score": "Average AI score",
    }
    return {
        "days": days,
        "generated_on": timezone.now().date().isoformat(),
        "summary": [
            {
                "metric": labels[name],
                "current": card["value"],
                "previous": card["previous"],
                "change": card["change"],
            }
            for name, card in cards.items()
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
    writer.writerow(["Metric", "This period", "Previous period", "Change"])
    for row in data["summary"]:
        writer.writerow([_safe(row[key]) for key in ("metric", "current", "previous", "change")])
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
