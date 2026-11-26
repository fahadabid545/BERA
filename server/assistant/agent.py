"""The company agent: answers one question from the company's own results, read only.

It talks to the AI through the one AI function (`ai.client.call_ai`), so the model settings, the
prompt versions, the token cap, the pause switch and the usage counting are the ones scoring uses.
The AI cannot touch the data itself: it may ask for one of the fixed read-only functions in
`tools.py` (a JSON `call`), the app runs it for the signed-in company and gives the result back,
until the AI gives its `answer`. Nothing the AI says can name a company, run anything else or
change anything; a reference to a candidate it was never shown is removed from the answer.

Nothing sent or received is logged. The call record holds only ids, the purpose and the tokens.
"""

import json
import re
from dataclasses import dataclass

from ai.client import AiPaused, AiUnavailable, call_ai
from ai.models import AiCall
from ai.prompt_versions import ASK, current_number, prompt_text
from core.errors import AppError
from platform_settings.service import get_setting

from . import tools

UNAVAILABLE_MESSAGE = "We could not answer right now. Please try again."
UNUSABLE_MESSAGE = "We could not give a usable answer. Please ask in another way."
REFERENCE = re.compile(r"\[(c_[0-9a-f]{8})\]")


@dataclass(frozen=True)
class Reply:
    answer: str
    refused: bool
    suggestions: list
    candidate_ids: list  # the candidates the answer names, in order


def _parsed(text):
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _suggestions(value):
    if not isinstance(value, list):
        return []
    longest = get_setting("ask.max_suggestion_length")
    cleaned = [item.strip()[:longest] for item in value if isinstance(item, str) and item.strip()]
    return cleaned[: get_setting("ask.max_suggestions")]


def _finished(turn, parsed):
    """The Reply for an `answer`, or None when it cannot be used."""
    answer = parsed.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return None
    answer = answer.strip()[: get_setting("ask.max_answer_length")]
    named = []
    for reference in REFERENCE.findall(answer):
        if reference in turn.known and reference not in named:
            named.append(reference)
    answer = REFERENCE.sub(
        lambda found: found.group(0) if found.group(1) in named else "", answer
    ).strip()
    return Reply(
        answer=answer,
        refused=parsed.get("refused") is True,
        suggestions=_suggestions(parsed.get("suggestions")),
        candidate_ids=[str(turn.known[reference]) for reference in named],
    )


def answer(company_id, question, earlier, known):
    """The `Reply` to `question`, or an AppError. `earlier` is the last messages of the chat as
    {"role", "text"} and `known` the candidates it already showed, {reference: candidate id}."""
    version = current_number(ASK)
    instructions = prompt_text(ASK, version)
    turn = tools.Turn(company_id=company_id, known=dict(known))
    results = []
    for _ in range(get_setting("ask.max_steps")):
        try:
            reply = call_ai(
                company_id,
                purpose=AiCall.Purpose.ASK,
                model=get_setting("ai.scoring_model"),
                instructions=instructions,
                text=json.dumps(
                    {
                        "functions": tools.catalogue(),
                        "earlier_messages": earlier,
                        "question": question,
                        "function_results": results,
                    }
                ),
                prompt_version=version,
                max_output_tokens=get_setting("ask.max_output_tokens"),
            )
        except AiPaused as paused:
            raise AppError("ai_paused", str(paused), status_code=503) from paused
        except AiUnavailable as unavailable:
            raise AppError("ask_unavailable", UNAVAILABLE_MESSAGE, status_code=503) from unavailable
        parsed = _parsed(reply.text)
        if parsed is None:
            break
        call = parsed.get("call")
        if isinstance(call, dict) and isinstance(call.get("name"), str):
            arguments = call.get("arguments", {})
            results.append(
                {
                    "function": call["name"],
                    "arguments": arguments,
                    "result": tools.run(turn, call["name"], arguments),
                }
            )
            continue
        if (finished := _finished(turn, parsed)) is not None:
            return finished
        break
    raise AppError("ask_unusable", UNUSABLE_MESSAGE, status_code=502)
