"""The functions the company agent may call. Every one only reads, and only for one company.

The company comes from the signed-in session, never from the AI or the question: a function has
no argument that names a company, and everything it reads is filtered by it. The agent has no
function that changes, deletes or sends anything, so a request to do so has nothing to run.

What a function returns is structured results only: references (`c_1a2b3c4d`, `p_5e6f7a8b`),
scores, grades, labels, stages, counts and requirement verdicts. It never returns a name, email,
phone, address, file name, CV text or an evidence quote: CV text is written by outsiders and could
carry instructions aimed at the AI. The contact details are put on the screen by the app, after the
AI has answered (see `cards.py`).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from django.db.models import Avg, Count, Max

from cvs.models import Candidate, RequirementResult
from platform_settings.service import get_setting
from projects.models import Project, Requirement

CANDIDATE_PREFIX, PROJECT_PREFIX = "c_", "p_"
REFERENCE_LENGTH = 8
SORTS = {"score": "score__score", "ats": "ats_score__score", "experience": None}


class ToolProblem(Exception):
    """The call cannot be run; the message is given back to the AI in plain words."""


def candidate_reference(candidate_id):
    return f"{CANDIDATE_PREFIX}{candidate_id.hex[:REFERENCE_LENGTH]}"


def project_reference(project_id):
    return f"{PROJECT_PREFIX}{project_id.hex[:REFERENCE_LENGTH]}"


@dataclass
class Turn:
    """What one question may refer to: the company, the candidates already shown in this chat
    (so "tell me more about the first one" works) and the ones this question's results showed."""

    company_id: object
    known: dict = field(default_factory=dict)  # candidate reference -> candidate id
    shown: list = field(default_factory=list)  # references shown in results, in order

    def remember(self, candidate):
        reference = candidate_reference(candidate.pk)
        self.known[reference] = candidate.pk
        if reference not in self.shown:
            self.shown.append(reference)
        return reference


def _project(turn, arguments, *, required):
    reference = arguments.get("project")
    if reference is None:
        if required:
            raise ToolProblem("Say which project (use its reference from list_projects).")
        return None
    for project in Project.objects.filter(company_id=turn.company_id):
        if project_reference(project.pk) == reference:
            return project
    raise ToolProblem("There is no project with that reference.")


def _candidate(turn, arguments):
    reference = arguments.get("candidate")
    candidate_id = turn.known.get(reference)
    candidate = (
        Candidate.objects.filter(company_id=turn.company_id, pk=candidate_id)
        .select_related("project", "profile")
        .first()
        if candidate_id
        else None
    )
    if candidate is None:
        raise ToolProblem("There is no candidate with that reference.")
    return candidate


def _number(arguments, name, low, high):
    value = arguments.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise ToolProblem(f"{name} must be a number from {low} to {high}.")
    return value


def _choice(arguments, name, allowed):
    value = arguments.get(name)
    if value is None:
        return None
    if value not in allowed:
        raise ToolProblem(f"{name} must be one of: {', '.join(sorted(allowed))}.")
    return value


def _only(arguments, names):
    unknown = set(arguments) - set(names)
    if unknown:
        raise ToolProblem(f"Unknown argument: {sorted(unknown)[0]}.")


def _years(candidate):
    years = candidate.profile.content.get("years_of_experience")
    return years if isinstance(years, int | float) and not isinstance(years, bool) else None


def _jobs_count(candidate):
    jobs = candidate.profile.content.get("jobs")
    return len(jobs) if isinstance(jobs, list) else None


def _ats(candidate):
    ats = getattr(candidate, "ats_score", None)
    return ats.score if ats else None


def _row(turn, candidate, *, with_project=False):
    score = candidate.score
    row = {
        "candidate": turn.remember(candidate),
        "score": f"{score.score:.1f}",
        "grade": score.grade,
        "label": score.label,
        "ats_score": _ats(candidate),
        "years_of_experience": _years(candidate),
        "stage": candidate.stage,
    }
    if with_project:
        row["project"] = project_reference(candidate.project_id)
    return row


def list_projects(turn, arguments):
    _only(arguments, [])
    projects = Project.objects.filter(company_id=turn.company_id).annotate(
        total=Count("candidates", distinct=True),
        scored=Count("candidates__score", distinct=True),
    )
    return {
        "projects": [
            {
                "project": project_reference(project.pk),
                "title": project.title,
                "status": project.status,
                "candidates": project.total,
                "scored_candidates": project.scored,
            }
            for project in projects.order_by("-created_at")[: get_setting("ask.max_projects")]
        ]
    }


def project_summary(turn, arguments):
    _only(arguments, ["project"])
    project = _project(turn, arguments, required=True)
    requirements = Requirement.objects.filter(project=project).order_by("position", "created_at")
    scored = Candidate.objects.filter(project=project, score__isnull=False)
    totals = scored.aggregate(best=Max("score__score"), average=Avg("score__score"))
    return {
        "project": project_reference(project.pk),
        "title": project.title,
        "requirements": [
            {"number": number, "kind": item.kind, "text": item.text}
            for number, item in enumerate(requirements, start=1)
        ],
        "candidates": Candidate.objects.filter(project=project).count(),
        "scored_candidates": scored.count(),
        "best_score": f"{totals['best']:.1f}" if totals["best"] is not None else None,
        "average_score": f"{totals['average']:.1f}" if totals["average"] is not None else None,
        "by_stage": dict(
            Candidate.objects.filter(project=project)
            .values_list("stage")
            .annotate(total=Count("id"))
        ),
    }


def find_candidates(turn, arguments):
    _only(arguments, ["project", "sort_by", "min_score", "stage", "limit"])
    project = _project(turn, arguments, required=False)
    sort_by = _choice(arguments, "sort_by", SORTS) or "score"
    minimum = _number(arguments, "min_score", 0, 100)
    stage = _choice(arguments, "stage", {value for value, _ in Candidate.Stage.choices})
    most = get_setting("ask.max_candidates")
    limit = int(_number(arguments, "limit", 1, most) or get_setting("ask.default_rows"))
    found = Candidate.objects.filter(company_id=turn.company_id, score__isnull=False)
    found = found.select_related("score", "profile", "ats_score")
    if project:
        found = found.filter(project=project)
    if minimum is not None:
        found = found.filter(score__score__gte=minimum)
    if stage:
        found = found.filter(stage=stage)
    if SORTS[sort_by]:
        rows = list(found.order_by(f"-{SORTS[sort_by]}", "created_at", "id")[:limit])
    else:
        # Years of experience live inside the profile, so they are sorted here; a CV with none
        # goes last.
        rows = sorted(
            found.order_by("created_at", "id"),
            key=lambda candidate: -(_years(candidate) if _years(candidate) is not None else -1),
        )[:limit]
    return {
        "matching": found.count(),
        "candidates": [_row(turn, candidate, with_project=project is None) for candidate in rows],
    }


def candidate_details(turn, arguments):
    _only(arguments, ["candidate"])
    candidate = _candidate(turn, arguments)
    score = getattr(candidate, "score", None)
    if score is None:
        raise ToolProblem("That candidate has no score yet.")
    numbers = {
        requirement.pk: number
        for number, requirement in enumerate(
            Requirement.objects.filter(project=candidate.project).order_by(
                "position", "created_at"
            ),
            start=1,
        )
    }
    verdicts = {
        numbers[requirement_id]: [verdict, confidence]
        for requirement_id, verdict, confidence in RequirementResult.objects.filter(
            candidate=candidate
        ).values_list("requirement_id", "verdict", "confidence")
        if requirement_id in numbers
    }
    ats = getattr(candidate, "ats_score", None)
    return {
        **_row(turn, candidate, with_project=True),
        "borderline": score.borderline,
        "jobs_count": _jobs_count(candidate),
        "ats_reasons": [reason.get("code", "") for reason in ats.reasons] if ats else [],
        "requirement_results": verdicts,
        "strengths": [item["requirement"] for item in score.strengths],
        "risks": [item["requirement"] for item in score.risks],
    }


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: dict
    run: Callable


TOOLS = {
    tool.name: tool
    for tool in (
        Tool(
            "list_projects",
            "Every project of the company with its reference, title and candidate counts.",
            {},
            list_projects,
        ),
        Tool(
            "project_summary",
            "One project's requirements (numbered), counts, best and average score, stages.",
            {"project": "a project reference"},
            project_summary,
        ),
        Tool(
            "find_candidates",
            "Scored candidates, best first. Leave project out to search every project.",
            {
                "project": "a project reference (optional)",
                "sort_by": "score, ats or experience (optional, default score)",
                "min_score": "0 to 100 (optional)",
                "stage": "new, shortlisted, interviewed, on_hold, selected or rejected (optional)",
                "limit": "how many to return (optional)",
            },
            find_candidates,
        ),
        Tool(
            "candidate_details",
            "One candidate's scores, ATS score, experience, stage, requirement verdicts, "
            "strengths and risks. Contact details are not available to you; the app shows them.",
            {"candidate": "a candidate reference you were given"},
            candidate_details,
        ),
    )
}


def catalogue():
    return [
        {"name": tool.name, "description": tool.description, "arguments": tool.arguments}
        for tool in TOOLS.values()
    ]


def run(turn, name, arguments):
    """The result of one call, or {"error": ...} in plain words; never an exception."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": "There is no such function."}
    if not isinstance(arguments, dict):
        return {"error": "Arguments must be an object."}
    try:
        return tool.run(turn, arguments)
    except ToolProblem as problem:
        return {"error": str(problem)}
