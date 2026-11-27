"""The extra figures of the company dashboard's Projects and Candidates tabs: one row for each
project, the projects that need a look, the CVs added each day, how the candidates split over the
flags and which requirements are missed most. All counted from stored data (no AI)."""

from datetime import timedelta

from django.db.models import Avg, Count, Max, Q

from plans.limits import CVS_PER_PROJECT, limit_for
from platform_settings.service import get_setting
from projects.models import Project, Requirement

from .models import Candidate, CvFile, RequirementResult

PERCENT = 100


def _projects(company_id):
    return list(
        Project.objects.filter(company_id=company_id, status=Project.Status.ACTIVE).order_by(
            "-updated_at"
        )
    )


def _rounded(value):
    return None if value is None else round(float(value), 1)


def project_rows(company_id):
    """One row for each active project: CVs held against what it can hold, how many are scored,
    the scores and how many candidates reached each flag."""
    projects = _projects(company_id)
    capacity = limit_for(company_id, CVS_PER_PROJECT)
    files = {
        row["project"]: row
        for row in CvFile.objects.filter(company_id=company_id)
        .values("project")
        .annotate(cvs=Count("pk"), failed=Count("pk", filter=Q(status=CvFile.Status.FAILED)))
    }
    stage = Candidate.Stage
    people = {
        row["project"]: row
        for row in Candidate.objects.filter(company_id=company_id)
        .values("project")
        .annotate(
            scored=Count("pk", filter=Q(score__isnull=False)),
            best=Max("score__score"),
            average=Avg("score__score"),
            ats_average=Avg("ats_score__score"),
            shortlisted=Count("pk", filter=Q(stage=stage.SHORTLISTED)),
            interviewed=Count("pk", filter=Q(stage=stage.INTERVIEWED)),
            selected=Count("pk", filter=Q(stage=stage.SELECTED)),
        )
    }
    return [
        {
            "id": str(project.pk),
            "title": project.title,
            "cvs": files.get(project.pk, {}).get("cvs", 0),
            "failed": files.get(project.pk, {}).get("failed", 0),
            "capacity": capacity,
            "scored": people.get(project.pk, {}).get("scored", 0),
            "best_score": _rounded(people.get(project.pk, {}).get("best")),
            "average_score": _rounded(people.get(project.pk, {}).get("average")),
            "ats_average": _rounded(people.get(project.pk, {}).get("ats_average")),
            "shortlisted": people.get(project.pk, {}).get("shortlisted", 0),
            "interviewed": people.get(project.pk, {}).get("interviewed", 0),
            "selected": people.get(project.pk, {}).get("selected", 0),
            "updated_at": project.updated_at.isoformat(),
        }
        for project in projects
    ]


def attention(rows):
    """The projects that need a look, one item for each reason: failed CVs, a project close to
    holding as many CVs as it can, and CVs uploaded but none scored."""
    warn_at = get_setting("dashboard.capacity_warning_percent")
    items = []
    for row in rows:
        if row["failed"]:
            items.append({**_ref(row), "reason": "failed", "count": row["failed"]})
        if row["capacity"] and row["cvs"] * PERCENT >= row["capacity"] * warn_at:
            items.append({**_ref(row), "reason": "almost_full", "count": row["cvs"]})
        if row["cvs"] and not row["scored"] and not row["failed"]:
            items.append({**_ref(row), "reason": "none_scored", "count": row["cvs"]})
    return items


def _ref(row):
    return {"id": row["id"], "title": row["title"], "capacity": row["capacity"]}


def uploads_per_day(company_id, start, days):
    """How many CVs were added on each of the `days` days from `start`."""
    found = dict(
        CvFile.objects.filter(
            company_id=company_id,
            created_at__date__gte=start,
            created_at__date__lt=start + timedelta(days=days),
        )
        .exclude(status=CvFile.Status.CANCELLED)
        .values_list("created_at__date")
        .annotate(total=Count("pk"))
    )
    return {
        "start": start.isoformat(),
        "values": [found.get(start + timedelta(days=offset), 0) for offset in range(days)],
    }


def flag_split(company_id):
    """How many candidates are at each flag."""
    found = dict(
        Candidate.objects.filter(company_id=company_id)
        .values_list("stage")
        .annotate(total=Count("pk"))
    )
    return [{"flag": value, "count": found.get(value, 0)} for value, _ in Candidate.Stage.choices]


def missed_requirements(company_id):
    """The requirements judged missing for the most candidates (a must-have first on a tie)."""
    rows = (
        RequirementResult.objects.filter(
            company_id=company_id, requirement__project__status=Project.Status.ACTIVE
        )
        .values("requirement")
        .annotate(
            missing=Count("pk", filter=Q(verdict=RequirementResult.Verdict.MISSING)),
            judged=Count("pk"),
        )
        .filter(missing__gt=0)
        .order_by("-missing", "requirement")[: get_setting("dashboard.missed_requirements_count")]
    )
    found = Requirement.objects.select_related("project").in_bulk(
        [row["requirement"] for row in rows]
    )
    return [
        {
            "requirement": found[row["requirement"]].text,
            "kind": found[row["requirement"]].kind,
            "project_id": str(found[row["requirement"]].project_id),
            "project_title": found[row["requirement"]].project.title,
            "missing": row["missing"],
            "judged": row["judged"],
        }
        for row in rows
    ]
