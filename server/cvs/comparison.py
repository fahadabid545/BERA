"""Comparing candidates of a project.

Two views, both read live from the stored results (nothing calls the AI), so a candidate whose CV
finishes later is in the matrix on its next look:

- Side by side: 2 to 4 chosen candidates, with their scores and each requirement's verdict and
  evidence next to each other (`GET .../compare/?ids=a,b`).
- Matrix: every candidate that passes the list's filters against every requirement, best score
  first, one page at a time (`GET .../matrix/`, the same query as the candidate list).
"""

from uuid import UUID

from django.http import Http404

from core.errors import AppError, form_error
from core.personal_data import mask_name
from platform_settings.service import get_setting
from projects.models import Requirement

from .detail import is_outdated
from .models import AtsScore, Candidate, CandidateScore, RequirementResult
from .ranking import filtered_rows, ordering
from .scoring import verdict_points

VERDICTS = ("met", "partly_met", "missing")


def _requirements(project):
    return list(Requirement.objects.filter(company_id=project.company_id, project=project))


def _requirement_entry(requirement):
    return {
        "id": str(requirement.pk),
        "text": requirement.text,
        "kind": requirement.kind,
        "weight": requirement.weight,
    }


def _chosen_ids(raw):
    pieces = [piece.strip() for piece in (raw or "").split(",") if piece.strip()]
    try:
        ids = list(dict.fromkeys(UUID(piece) for piece in pieces))
    except ValueError:
        raise Http404 from None
    least, most = get_setting("comparison.min_candidates"), get_setting("comparison.max_candidates")
    if len(ids) > most:
        raise AppError(
            "too_many_to_compare",
            f"You can compare up to {most} candidates at a time. Choose fewer.",
            status_code=400,
        )
    if len(ids) < least:
        raise form_error({"ids": f"Choose at least {least} candidates to compare."})
    return ids


def _judgements(candidate_ids):
    return {
        (item.candidate_id, item.requirement_id): item
        for item in RequirementResult.objects.filter(candidate_id__in=candidate_ids)
    }


def side_by_side(project, params):
    """The chosen candidates (in the order chosen) and the project's requirements. A candidate
    that is not in this project makes the whole request "not found"."""
    ids = _chosen_ids(params.get("ids"))
    found = {
        candidate.pk: candidate
        for candidate in Candidate.objects.filter(
            company_id=project.company_id, project=project, pk__in=ids
        ).select_related("cv_file", "contact")
    }
    if len(found) != len(ids):
        raise Http404
    requirements = _requirements(project)
    judged = _judgements(ids)
    scores = {
        item.candidate_id: item for item in CandidateScore.objects.filter(candidate_id__in=ids)
    }
    ats = {item.candidate_id: item.score for item in AtsScore.objects.filter(candidate_id__in=ids)}
    candidates = []
    for pk in ids:
        candidate, score = found[pk], scores.get(pk)
        candidates.append(
            {
                "id": str(pk),
                "file_name": candidate.cv_file.original_name,
                "name": mask_name(candidate.contact.name) if candidate.contact.name else "",
                "stage": candidate.stage,
                "score": f"{score.score:.1f}" if score else None,
                "grade": score.grade if score else None,
                "outdated": bool(score and score.outdated),
                "label": score.label if score else None,
                "borderline": bool(score and score.borderline),
                "ats_score": ats.get(pk),
                "must_score": _one_decimal(score.must_score if score else None),
                "nice_score": _one_decimal(score.nice_score if score else None),
                "capped": bool(score and score.capped),
                "results": [
                    _cell(requirement, judged.get((pk, requirement.pk)), with_evidence=True)
                    for requirement in requirements
                ],
            }
        )
    for item in candidates:
        item["summary"] = _summary(requirements, item["results"])
    return {
        "requirements": [_requirement_entry(item) for item in requirements],
        "candidates": candidates,
        "insights": _insights(requirements, candidates),
        "points": {key: float(value) for key, value in verdict_points().items()},
    }


def _one_decimal(value):
    return None if value is None else f"{value:.1f}"


def _summary(requirements, results):
    """For each group (must-have, nice-to-have): how many requirements were met, partly met,
    missing, or not judged yet."""
    summary = {kind: dict.fromkeys((*VERDICTS, "not_judged"), 0) for kind in ("must", "nice")}
    for requirement, cell in zip(requirements, results, strict=True):
        summary[requirement.kind][cell["verdict"] or "not_judged"] += 1
    return summary


def _insights(requirements, candidates):
    """Plain facts about how the chosen candidates differ, as data (the page words them):

    - lead: who has the highest AI score and by how many points over the next (or a tie).
    - must_gap: a candidate with must-haves that are missing.
    - best_on: requirements where one candidate is clearly the best (others are behind)."""
    facts = []
    scored = sorted(
        (item for item in candidates if item["score"] is not None),
        key=lambda item: float(item["score"]),
        reverse=True,
    )
    if len(scored) >= 2:
        top, next_best = float(scored[0]["score"]), float(scored[1]["score"])
        if top == next_best:
            tied = [item["id"] for item in scored if float(item["score"]) == top]
            facts.append({"kind": "tie", "candidates": tied})
        else:
            facts.append(
                {
                    "kind": "lead",
                    "candidate": scored[0]["id"],
                    "over": scored[1]["id"],
                    "points": round(top - next_best, 1),
                }
            )
    for item in candidates:
        gaps = [
            str(requirement.pk)
            for requirement, cell in zip(requirements, item["results"], strict=True)
            if requirement.kind == "must" and cell["verdict"] == "missing"
        ]
        if gaps:
            facts.append({"kind": "must_gap", "candidate": item["id"], "requirements": gaps})
    if len(candidates) >= 2:
        points = verdict_points()
        best = {}
        for index, requirement in enumerate(requirements):
            values = {
                item["id"]: points[item["results"][index]["verdict"]]
                for item in candidates
                if item["results"][index]["verdict"]
            }
            if len(values) < len(candidates) or len(set(values.values())) < 2:
                continue
            top = max(values.values())
            winners = [key for key, value in values.items() if value == top]
            if len(winners) == 1:
                best.setdefault(winners[0], []).append(str(requirement.pk))
        for candidate_id, ids in best.items():
            facts.append({"kind": "best_on", "candidate": candidate_id, "requirements": ids})
    return facts


def _cell(requirement, judgement, *, with_evidence=False):
    cell = {
        "verdict": judgement.verdict if judgement else None,
        "outdated": is_outdated(requirement, judgement),
    }
    if with_evidence:
        cell["evidence"] = judgement.evidence if judgement else ""
        cell["confidence"] = judgement.confidence if judgement else None
    return cell


def matrix(project, params):
    """One page of the candidates passing the filters against all the requirements."""
    rows, filters = filtered_rows(project, params)
    try:
        page = int(params.get("page") or 1)
        if page < 1:
            raise ValueError
    except ValueError:
        raise form_error({"page": "The page is a number from 1."}) from None
    rows = rows.filter(candidate_pk__isnull=False)
    size = get_setting("comparison.matrix_page_size")
    total = rows.count()
    pages = max(1, -(-total // size))
    page = min(page, pages)
    window = list(rows.order_by(*ordering("score", "desc"))[(page - 1) * size : page * size])
    requirements = _requirements(project)
    judged = _judgements([item.candidate_pk for item in window])
    return {
        "page": page,
        "pages": pages,
        "count": total,
        "filtered": bool(filters),
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "requirements": [_requirement_entry(item) for item in requirements],
        "rows": [
            {
                "candidate_id": str(item.candidate_pk),
                "file_name": item.original_name,
                "name": mask_name(item.contact_name) if item.contact_name else "",
                "rank": item.ranking if item.score_value is not None else None,
                "score": f"{item.score_value:.1f}" if item.score_value is not None else None,
                "grade": item.grade_value,
                "cells": [
                    _cell(requirement, judged.get((item.candidate_pk, requirement.pk)))
                    for requirement in requirements
                ],
            }
            for item in window
        ],
    }
