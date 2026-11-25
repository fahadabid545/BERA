"""Everything about one candidate, for the candidate page (`GET .../candidates/<id>/`).

The contact details are shown here and nowhere else. After a change to the project the page shows
the latest stored results and marks what is out of date: the score while re-scoring is due, a
requirement whose wording changed since it was judged (or that was never judged), and extra
factors worked out for an earlier job description. Nothing here calls the AI.
"""

from projects.models import Requirement

from .downloads import PREVIEW_TYPES
from .extra_factors import stored_factors
from .models import AtsScore, CandidateScore, RequirementResult
from .notes import notes_of
from .stages import history


def _contact(candidate):
    contact = candidate.contact
    return {
        "name": contact.name,
        "email": contact.email,
        "phone": contact.phone,
        "address": contact.address,
    }


def score_block(candidate):
    score = CandidateScore.objects.filter(candidate=candidate).first()
    if score is None:
        return None
    return {
        "score": f"{score.score:.1f}",
        "grade": score.grade,
        "capped": score.capped,
        "outdated": score.outdated,
        "must_score": f"{score.must_score:.1f}" if score.must_score is not None else None,
        "nice_score": f"{score.nice_score:.1f}" if score.nice_score is not None else None,
        "label": score.label,
        "borderline": score.borderline,
        "strengths": score.strengths,
        "risks": score.risks,
        "interview_questions": score.interview_questions,
        "guide_note": score.guide_note,
    }


def ats_block(candidate):
    ats = AtsScore.objects.filter(candidate=candidate).first()
    if ats is None:
        return None
    return {"score": ats.score, "reasons": ats.reasons, "rules_version": ats.rules_version}


def is_outdated(requirement, judged):
    """Never judged, or judged against wording the requirement no longer has."""
    return judged is None or judged.requirement_text != requirement.text


def requirement_results(candidate, results):
    """One entry for each requirement of the project, in the project's order. A requirement not
    judged yet has no verdict; one judged against older wording is marked outdated."""
    by_requirement = {item.requirement_id: item for item in results}
    entries = []
    for requirement in Requirement.objects.filter(
        company_id=candidate.company_id, project_id=candidate.project_id
    ):
        judged = by_requirement.get(requirement.pk)
        entries.append(
            {
                "requirement_id": str(requirement.pk),
                "text": requirement.text,
                "kind": requirement.kind,
                "weight": requirement.weight,
                "verdict": judged.verdict if judged else None,
                "evidence": judged.evidence if judged else "",
                "confidence": judged.confidence if judged else None,
                "outdated": is_outdated(requirement, judged),
            }
        )
    return entries


def _factors(candidate):
    stored = stored_factors(candidate)
    if stored is None:
        return None
    values, outdated = stored
    return {"outdated": outdated, "values": values}


def _versions(candidate, results):
    """The model and prompt version behind the reading and behind the latest judgements."""
    judged = max(results, key=lambda item: item.created_at, default=None)
    return {
        "reading": {
            "model": candidate.profile.model,
            "prompt_version": candidate.profile.prompt_version,
        },
        "scoring": (
            {"model": judged.model, "prompt_version": judged.prompt_version} if judged else None
        ),
    }


def candidate_detail(candidate, user_id):
    cv_file = candidate.cv_file
    results = list(RequirementResult.objects.filter(candidate=candidate))
    return {
        "id": str(candidate.pk),
        "file_name": cv_file.original_name,
        "status": cv_file.status,
        "failure_reason": cv_file.failure_reason,
        "stage": candidate.stage,
        "added_at": candidate.created_at.isoformat(),
        "contact": _contact(candidate),
        "score": score_block(candidate),
        "ats": ats_block(candidate),
        "requirements": requirement_results(candidate, results),
        "factors": _factors(candidate),
        "history": history(candidate),
        "notes": notes_of(candidate, user_id),
        "models": _versions(candidate, results),
        "cv": {
            "file_type": cv_file.file_type,
            "can_preview": cv_file.file_type in PREVIEW_TYPES,
        },
    }
