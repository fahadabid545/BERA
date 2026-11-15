"""The numbers behind the dashboard charts, for one project or for the whole company.

Each chart answers one question, and everything is counted from stored data when asked (no AI):

- funnel: how far do the CVs get? Uploaded, read, scored, then how many scored candidates have
  ever reached Shortlisted, Interview and Approved (a candidate rejected later still counts for
  the stages it reached, and each step is a part of the one before it).
- distribution: how are the scored candidates spread over the grades?
- ranking (project): who is at the top? The best candidates by AI score.
- coverage (project): how well do the candidates meet each requirement? A verdict counts only
  while the requirement still has the wording it was judged against.
- trend: is it more or less than before? CVs uploaded and CVs scored per day over the last N
  days, next to the N days before them, with the change in percent.
"""

from datetime import timedelta

from django.db.models import Count, Exists, F, OuterRef, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.errors import form_error
from core.personal_data import mask_name
from platform_settings.service import get_setting
from projects.models import Requirement

from .models import Candidate, CandidateScore, CvFile, RequirementResult, StageChange
from .scoring import GRADE_LIMITS, LOWEST_GRADE
from .top_list import top_scores

GRADES = [grade for grade, _ in GRADE_LIMITS] + [LOWEST_GRADE]
# Stages a candidate has reached once it is in, or has been in, one of these.
REACHED = (
    (
        "shortlisted",
        (Candidate.Stage.SHORTLISTED, Candidate.Stage.INTERVIEW, Candidate.Stage.APPROVED),
    ),
    ("interview", (Candidate.Stage.INTERVIEW, Candidate.Stage.APPROVED)),
    ("approved", (Candidate.Stage.APPROVED,)),
)
PERCENT = 100


def _scope(company_id, project):
    """The filter that keeps a model to the company, and to the project when one is given."""
    return {"company_id": company_id, **({"project": project} if project else {})}


def _candidate_scope(company_id, project):
    return {"company_id": company_id, **({"candidate__project": project} if project else {})}


def funnel(company_id, project=None):
    cvs = CvFile.objects.filter(**_scope(company_id, project)).exclude(
        status=CvFile.Status.CANCELLED
    )
    candidates = Candidate.objects.filter(**_scope(company_id, project))
    scored = candidates.filter(score__isnull=False)
    steps = [
        ("uploaded", cvs.count()),
        ("read", candidates.count()),
        ("scored", scored.count()),
    ]
    for name, stages in REACHED:
        reached = Exists(StageChange.objects.filter(candidate=OuterRef("pk"), to_stage__in=stages))
        steps.append((name, scored.filter(Q(stage__in=stages) | reached).count()))
    return [{"step": name, "count": count} for name, count in steps]


def distribution(company_id, project=None):
    found = dict(
        CandidateScore.objects.filter(**_candidate_scope(company_id, project))
        .values_list("grade")
        .annotate(total=Count("pk"))
    )
    return [{"grade": grade, "count": found.get(grade, 0)} for grade in GRADES]


def ranking(project):
    shown = get_setting("charts.ranking_max_bars")
    return [
        {
            "rank": rank,
            "candidate_id": str(item.candidate_id),
            "file_name": item.candidate.cv_file.original_name,
            "name": mask_name(item.candidate.contact.name) if item.candidate.contact.name else "",
            "score": f"{item.score:.1f}",
            "grade": item.grade,
        }
        for rank, item in enumerate(top_scores(project)[:shown], start=1)
    ]


def coverage(project):
    scored = Candidate.objects.filter(
        company_id=project.company_id, project=project, score__isnull=False
    ).count()
    found = {}
    judged = RequirementResult.objects.filter(
        company_id=project.company_id,
        candidate__project=project,
        candidate__score__isnull=False,
        requirement_text=F("requirement__text"),
    )
    for requirement_id, verdict, total in judged.values_list("requirement_id", "verdict").annotate(
        total=Count("pk")
    ):
        found.setdefault(requirement_id, {})[verdict] = total
    entries = []
    for requirement in Requirement.objects.filter(company_id=project.company_id, project=project):
        counts = found.get(requirement.pk, {})
        met, partly, missing = (counts.get(v, 0) for v in ("met", "partly_met", "missing"))
        entries.append(
            {
                "requirement_id": str(requirement.pk),
                "text": requirement.text,
                "kind": requirement.kind,
                "met": met,
                "partly_met": partly,
                "missing": missing,
                "not_judged": scored - met - partly - missing,
            }
        )
    return {"candidates": scored, "requirements": entries}


def _per_day(queryset, column, first, days):
    counts = dict(
        queryset.filter(
            **{f"{column}__date__gte": first, f"{column}__date__lt": first + timedelta(days=days)}
        )
        .annotate(day=TruncDate(column))
        .values_list("day")
        .annotate(total=Count("pk"))
    )
    return [counts.get(first + timedelta(days=offset), 0) for offset in range(days)]


def _change(current, previous):
    """Percent change against the previous period; None when there was nothing before."""
    return round((current - previous) * PERCENT / previous, 1) if previous else None


def checked_days(raw):
    choices = get_setting("charts.trend_days_choices")
    try:
        days = get_setting("charts.trend_days_default") if raw in (None, "") else int(raw)
    except ValueError:
        days = None
    if days not in choices:
        raise form_error({"days": "Choose one of the offered periods."})
    return days


def trend(company_id, project, days):
    """Per day counts for the last `days` days (today included) and for the `days` before."""
    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    before = start - timedelta(days=days)
    uploads = CvFile.objects.filter(**_scope(company_id, project)).exclude(
        status=CvFile.Status.CANCELLED
    )
    scores = CandidateScore.objects.filter(**_candidate_scope(company_id, project))
    metrics = {}
    for name, queryset, column in (
        ("uploaded", uploads, "created_at"),
        ("scored", scores, "created_at"),
    ):
        current = _per_day(queryset, column, start, days)
        previous = _per_day(queryset, column, before, days)
        metrics[name] = {
            "current": current,
            "previous": previous,
            "total": sum(current),
            "previous_total": sum(previous),
            "change_percent": _change(sum(current), sum(previous)),
        }
    return {
        "days": days,
        "choices": get_setting("charts.trend_days_choices"),
        "start": start.isoformat(),
        "previous_start": before.isoformat(),
        "metrics": metrics,
    }


def project_charts(project, raw_days):
    days = checked_days(raw_days)
    company_id = project.company_id
    return {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "funnel": funnel(company_id, project),
        "distribution": distribution(company_id, project),
        "ranking": ranking(project),
        "coverage": coverage(project),
        "trend": trend(company_id, project, days),
    }


def company_charts(company_id, raw_days):
    days = checked_days(raw_days)
    return {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "funnel": funnel(company_id),
        "distribution": distribution(company_id),
        "trend": trend(company_id, None, days),
    }
