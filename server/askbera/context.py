"""What Ask Bera's AI is allowed to see about a project: structured results only.

It holds a reference for each candidate (C1, C2, ... by rank, valid for one question only), the
score, grade, label, stage, the verdict and confidence for each requirement, and the strengths and
risks (which quote only the requirement wording). It never holds a name, email, phone, address,
file name, CV text or an evidence quote: CV text is written by outsiders and could carry
instructions aimed at the AI, so it must never reach this feature.
"""

from django.db.models import Count

from cvs.models import Candidate, RequirementResult
from platform_settings.service import get_setting
from projects.models import Requirement


def _requirements(project):
    return list(Requirement.objects.filter(project=project).order_by("position", "created_at"))


def _ranked_candidates(project):
    return list(
        Candidate.objects.filter(
            company_id=project.company_id, project=project, score__isnull=False
        )
        .select_related("score")
        .order_by("-score__score", "created_at", "id")
    )


def _candidate_block(reference, candidate, verdicts):
    score = candidate.score
    return {
        "reference": reference,
        "score": f"{score.score:.1f}",
        "grade": score.grade,
        "label": score.label,
        "borderline": score.borderline,
        "stage": candidate.stage,
        "results": verdicts,
        "strengths": [item["requirement"] for item in score.strengths],
        "risks": [item["requirement"] for item in score.risks],
    }


def _verdicts_by_candidate(candidates, numbers):
    """{candidate id: {requirement number: [verdict, confidence]}} (numbers are 1, 2, ... in the
    order the requirements are listed to the AI)."""
    verdicts = {candidate.pk: {} for candidate in candidates}
    rows = RequirementResult.objects.filter(candidate__in=candidates).values_list(
        "candidate_id", "requirement_id", "verdict", "confidence"
    )
    for candidate_id, requirement_id, verdict, confidence in rows:
        if requirement_id in numbers:
            verdicts[candidate_id][numbers[requirement_id]] = [verdict, confidence]
    return verdicts


def build(project):
    """(data for the AI, {reference: Candidate}). Only the best `ask.max_candidates` candidates
    are sent; the counts always cover all of them."""
    requirements = _requirements(project)
    numbers = {requirement.pk: number for number, requirement in enumerate(requirements, start=1)}
    ranked = _ranked_candidates(project)
    shown = ranked[: get_setting("ask.max_candidates")]
    verdicts = _verdicts_by_candidate(shown, numbers)
    references = {f"C{position}": candidate for position, candidate in enumerate(shown, start=1)}
    stages = dict(
        Candidate.objects.filter(company_id=project.company_id, project=project)
        .values_list("stage")
        .annotate(total=Count("id"))
    )
    data = {
        "requirements": [
            {"number": numbers[requirement.pk], "kind": requirement.kind, "text": requirement.text}
            for requirement in requirements
        ],
        "counts": {
            "scored_candidates": len(ranked),
            "candidates_shown": len(shown),
            "by_stage": stages,
        },
        "candidates": [
            _candidate_block(reference, candidate, verdicts[candidate.pk])
            for reference, candidate in references.items()
        ],
    }
    return data, references
