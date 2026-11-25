"""Ask Bera: a recruiter asks a question about one project's candidates in plain language.

Read only by construction: the AI gets no tools, only structured results (see `context.py`), and
its answer is plain text. The project and company come from the signed-in session, never from the
question or the answer. Nothing is stored: no question, no answer, no history; the call record
holds only ids, the purpose and the tokens (see `ai.client`). Nothing sent or received is logged.
"""

import json
import re

from ai.client import AiPaused, AiUnavailable, call_ai
from ai.models import AiCall
from ai.prompt_versions import ASK, current_number, prompt_text
from core.errors import AppError
from core.personal_data import mask_name
from plans.limits import check_ai_allowed
from platform_settings.service import get_setting

from . import context

UNAVAILABLE_MESSAGE = "We could not answer right now. Please try again."
UNUSABLE_MESSAGE = "We could not give a usable answer. Please ask in another way."
NO_RESULTS_MESSAGE = "There are no scored candidates in this project yet."
REFERENCE = re.compile(r"\[(C\d+)\]")


def _answer_from(text):
    """(answer, refused) from the AI's JSON, or None when it cannot be used."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        return None
    answer = parsed["answer"].strip()
    if not answer:
        return None
    return answer[: get_setting("ask.max_answer_length")], parsed.get("refused") is True


def _shown_candidates(answer, references):
    """The candidates the answer mentions, in order, as {reference, candidate_id, initials}. A
    reference the question's data did not have is not a candidate and is removed from the text."""
    mentioned = []
    for reference in REFERENCE.findall(answer):
        if reference in references and reference not in mentioned:
            mentioned.append(reference)
    return mentioned


def _described(reference, candidate):
    return {
        "reference": reference,
        "candidate_id": str(candidate.pk),
        "initials": mask_name(candidate.contact.name),
    }


def ask(project, question):
    """{"answer", "refused", "candidates"} for the question, or an AppError. The shared limits
    apply as they do to scoring: the plan's AI allowance, the pause switch and an outage."""
    check_ai_allowed(project.company_id).raise_if_blocked()
    data, references = context.build(project)
    if not references:
        raise AppError("ask_no_results", NO_RESULTS_MESSAGE, status_code=409)
    version = current_number(ASK)
    try:
        reply = call_ai(
            project.company_id,
            purpose=AiCall.Purpose.ASK,
            model=project.scoring_model,
            instructions=prompt_text(ASK, version),
            text=json.dumps({"question": question, "project": data}),
            prompt_version=version,
            project_id=project.pk,
            max_output_tokens=get_setting("ask.max_output_tokens"),
        )
    except AiPaused as paused:
        raise AppError("ai_paused", str(paused), status_code=503) from paused
    except AiUnavailable as unavailable:
        raise AppError("ask_unavailable", UNAVAILABLE_MESSAGE, status_code=503) from unavailable
    understood = _answer_from(reply.text)
    if understood is None:
        raise AppError("ask_unusable", UNUSABLE_MESSAGE, status_code=502)
    answer, refused = understood
    mentioned = _shown_candidates(answer, references)
    answer = REFERENCE.sub(
        lambda found: found.group(0) if found.group(1) in mentioned else "", answer
    )
    return {
        "answer": answer.strip(),
        "refused": refused,
        "candidates": [_described(reference, references[reference]) for reference in mentioned],
    }
