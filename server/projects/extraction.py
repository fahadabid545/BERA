"""Proposing requirements from a project's job description.

The AI only proposes: nothing is saved here. The Requirement editor lets the user edit and
confirm before anything is used. Whatever the AI answers is treated as untrusted text and is
checked strictly; an unusable answer or an unavailable AI falls back to manual entry.
"""

import json
import logging

from ai.client import AiPaused, AiUnavailable, call_ai
from ai.models import AiCall
from plans.limits import check_ai_allowed
from platform_settings.service import get_setting

from .service import require_editable

logger = logging.getLogger(__name__)

KINDS = ("must", "nice")
ENGLISH = "en"
SHORT_DESCRIPTION_WARNING = "short_description"
OTHER_LANGUAGE_WARNING = "other_language"
TRIMMED_WARNING = "trimmed"
FALLBACK_MESSAGE = (
    "We could not suggest requirements this time. You can enter them yourself, or try again later."
)


def _checked_weight(value, heaviest):
    """The AI's weight when it is a whole number in range; otherwise the default, because a
    requirement with a doubtful weight is still worth keeping."""
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= heaviest:
        return value
    return get_setting("requirements.weight_default")


def _clean_requirements(items):
    """The valid, distinct entries in the AI's order. Anything malformed or too long is
    dropped rather than cut short, so a requirement is never changed in meaning."""
    longest = get_setting("requirements.max_length")
    seen, cleaned = set(), []
    heaviest = get_setting("requirements.weight_max")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        kind, text = item.get("kind"), item.get("text")
        if kind not in KINDS or not isinstance(text, str):
            continue
        text = " ".join(text.split())
        if not text or len(text) > longest or text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(
            {"kind": kind, "text": text, "weight": _checked_weight(item.get("weight"), heaviest)}
        )
    return cleaned


def parse_answer(raw_text):
    """(language, requirements) from the AI's JSON, or None when it cannot be used."""
    try:
        answer = json.loads(raw_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(answer, dict):
        return None
    cleaned = _clean_requirements(answer.get("requirements"))
    if not cleaned:
        return None
    language = answer.get("language")
    return (language.strip().lower() if isinstance(language, str) else ""), cleaned


def _fallback(message=FALLBACK_MESSAGE):
    return {"requirements": [], "warnings": [], "fallback": True, "message": message}


def request_requirements(
    job_description, *, company_id, model, purpose, project_id=None, ask=call_ai
):
    """(language, requirements) from the AI for a job description, or None when its answer cannot
    be used. `ask` is `call_ai`, or a wrapper the AI playground uses to count a test run."""
    answer = ask(
        company_id,
        purpose=purpose,
        model=model,
        instructions=get_setting("ai.requirement_extraction_prompt"),
        text=job_description,
        project_id=project_id,
    )
    return parse_answer(answer.text)


def suggest_requirements(project):
    """Must-have and nice-to-have requirements for the project, up to the platform's total,
    with warnings. The model is the one pinned to the project."""
    require_editable(project)
    check_ai_allowed(project.company_id).raise_if_blocked()
    try:
        parsed = request_requirements(
            project.job_description,
            company_id=project.company_id,
            model=project.reading_model,
            purpose=AiCall.Purpose.REQUIREMENT_EXTRACTION,
            project_id=project.pk,
        )
    except AiPaused as paused:
        return _fallback(str(paused))
    except AiUnavailable:
        return _fallback()
    if parsed is None:
        logger.warning("The AI gave requirements that could not be used.")
        return _fallback()

    language, requirements = parsed
    warnings = []
    limit = get_setting("requirements.max_total")
    if len(requirements) > limit:
        requirements = requirements[:limit]
        warnings.append(
            {
                "code": TRIMMED_WARNING,
                "message": f"Only the first {limit} requirements are shown.",
            }
        )
    if len(project.job_description) < get_setting("projects.short_description_length"):
        warnings.append(
            {
                "code": SHORT_DESCRIPTION_WARNING,
                "message": "This description is short, so few requirements were found. "
                "Add more detail or enter them yourself.",
            }
        )
    if language and language != ENGLISH:
        warnings.append(
            {
                "code": OTHER_LANGUAGE_WARNING,
                "message": "This description is not in English. Check the requirements "
                "carefully before using them.",
            }
        )
    return {"requirements": requirements, "warnings": warnings, "fallback": False, "message": ""}
