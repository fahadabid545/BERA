"""The Pareto frontier of a project's candidates: who is not beaten on both of two scores.

A candidate is on the frontier when no other candidate is at least as high on both scores and
higher on one. These are the candidates worth comparing: every other candidate has someone who
is better on both. Two pairs of scores can be set against each other:

- ai_ats: the AI score (how well the CV meets the requirements) against the ATS score (how well
  the CV is built to be read by an applicant tracking system).
- must_nice: the must-have score against the nice-to-have score.

Only scored candidates who are not rejected, and who have both scores, are placed.
"""

from core.errors import form_error
from core.personal_data import mask_name
from platform_settings.service import get_setting

from .models import Candidate

# (vertical score, horizontal score)
AXES = {"ai_ats": ("ai", "ats"), "must_nice": ("must", "nice")}
DEFAULT_AXES = "ai_ats"


def _values(candidate, axes):
    score = candidate.score
    if axes == "ai_ats":
        ats = getattr(candidate, "ats_score", None)
        return (float(score.score), float(ats.score)) if ats else None
    if score.must_score is None or score.nice_score is None:
        return None
    return float(score.must_score), float(score.nice_score)


def pareto(points):
    """The ids of the points nobody beats, and for each beaten point the id of one that does.
    `points` is a list of (id, x, y). Equal points do not beat each other."""
    ordered = sorted(points, key=lambda point: (-point[1], -point[2]))
    frontier, best_y, index = [], float("-inf"), 0
    while index < len(ordered):
        same_x = [point for point in ordered[index:] if point[1] == ordered[index][1]]
        index += len(same_x)
        top_in_group = max(point[2] for point in same_x)
        for point in same_x:
            if point[2] > best_y and point[2] == top_in_group:
                frontier.append(point)
        best_y = max(best_y, top_in_group)
    beaten_by = {}
    leaders = sorted(frontier, key=lambda point: -(point[1] + point[2]))
    for point in points:
        if point in frontier:
            continue
        beaten_by[point[0]] = next(
            lead[0] for lead in leaders if lead[1] >= point[1] and lead[2] >= point[2]
        )
    return [point[0] for point in sorted(frontier, key=lambda point: point[1])], beaten_by


def frontier(project, params):
    axes = params.get("axes") or DEFAULT_AXES
    if axes not in AXES:
        raise form_error({"axes": "Choose one of the offered pairs of scores."})
    candidates = (
        Candidate.objects.filter(
            company_id=project.company_id, project=project, score__isnull=False
        )
        .exclude(stage=Candidate.Stage.REJECTED)
        .select_related("contact", "cv_file", "score", "ats_score")
    )
    placed, left_out = [], 0
    for candidate in candidates:
        values = _values(candidate, axes)
        if values is None:
            left_out += 1
        else:
            placed.append((candidate, values))
    on_frontier, beaten_by = pareto([(str(candidate.pk), x, y) for candidate, (y, x) in placed])
    shown = sorted(placed, key=lambda item: -item[1][0])
    limit = get_setting("comparison.frontier_max_points")
    keep = [item for item in shown if str(item[0].pk) in on_frontier]
    keep += [item for item in shown if str(item[0].pk) not in on_frontier][
        : max(0, limit - len(keep))
    ]
    return {
        "axes": axes,
        "choices": list(AXES),
        "compare_limits": {
            "min": get_setting("comparison.min_candidates"),
            "max": get_setting("comparison.max_candidates"),
        },
        "total": len(placed),
        "left_out": left_out,
        "frontier": on_frontier,
        "points": [
            {
                "id": str(candidate.pk),
                "name": mask_name(candidate.contact.name) if candidate.contact.name else "",
                "file_name": candidate.cv_file.original_name,
                "grade": candidate.score.grade,
                "stage": candidate.stage,
                "x": x,
                "y": y,
                "beaten_by": beaten_by.get(str(candidate.pk)),
            }
            for candidate, (y, x) in keep
        ],
    }
