"""Proposing requirements from a project's job description.

The AI only proposes: nothing is saved here. The Requirement editor lets the user edit and
confirm before anything is used. Whatever the AI answers is treated as untrusted text and is
checked strictly; an unusable answer or an unavailable AI falls back to manual entry.
"""

import json
import logging

from ai.client import AiUnavailable, call_ai
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


def _clean_requirements(items):
    """The valid, distinct entries in the AI's order. Anything malformed or too long is
    dropped rather than cut short, so a requirement is never changed in meaning."""
    longest = get_setting("requirements.max_length")
    seen, cleaned = set(), []
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
        cleaned.append({"kind": kind, "text": text})
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


def _fallback():
    return {"requirements": [], "warnings": [], "fallback": True, "message": FALLBACK_MESSAGE}


def suggest_requirements(project):
    """Must-have and nice-to-have requirements for the project, up to the platform's total,
    with warnings. The model is the one pinned to the project."""
    require_editable(project)
    check_ai_allowed(project.company_id).raise_if_blocked()
    try:
        answer = call_ai(
            project.company_id,
            purpose=AiCall.Purpose.REQUIREMENT_EXTRACTION,
            model=project.reading_model,
            instructions=get_setting("ai.requirement_extraction_prompt"),
            text=project.job_description,
            project_id=project.pk,
        )
    except AiUnavailable:
        return _fallback()
    parsed = parse_answer(answer.text)
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
