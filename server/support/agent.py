"""The support agent: talks with one person about a problem and either helps or hands it to the
support team as a ticket.

It talks to the AI through the one AI function (`ai.client.call_ai`), so the model settings, the
prompt version and the usage counting are the ones everything else uses. It is given only what
the person wrote and the public product documents (`chatbot.knowledge`); it can read no company
data and cannot do anything. A hand-over carries a fixed shape of short parts; whatever the AI
sends is cut to length and checked, and a category it invents becomes "other".

Nothing sent or received is logged. The call record holds only ids, the purpose and the tokens.
"""

import json
from dataclasses import dataclass

from ai.client import AiUnavailable, call_ai
from ai.models import AiCall
from ai.prompt_versions import SUPPORT, current_number, prompt_text
from chatbot import knowledge
from platform_settings.service import get_setting

from .models import SupportTicket

PARTS = ("summary", "what_happened", "expected", "steps")


@dataclass(frozen=True)
class Handover:
    title: str
    category: str
    summary: str
    what_happened: str
    expected: str
    steps: str


@dataclass(frozen=True)
class Turn:
    reply: str
    handover: Handover | None  # set when the problem goes to the support team


def _text(value, longest):
    return value.strip()[:longest] if isinstance(value, str) else ""


def _handover(found):
    longest = get_setting("support.max_field_length")
    category = found.get("category")
    title = _text(found.get("title"), get_setting("support.max_title_length"))
    parts = {name: _text(found.get(name), longest) for name in PARTS}
    if not title or not parts["summary"]:
        return None
    return Handover(
        title=title,
        category=category if category in SupportTicket.Category.values else "other",
        **parts,
    )


def _parsed(text):
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def next_turn(company_id, message, earlier):
    """The `Turn` for the person's message, or None when the AI cannot give a usable one (paused,
    unavailable or not in the shape asked for): the caller then hands the problem to the team
    itself, so a person is never left without a way to reach support."""
    version = current_number(SUPPORT)
    try:
        reply = call_ai(
            company_id,
            purpose=AiCall.Purpose.SUPPORT,
            model=get_setting("ai.scoring_model"),
            instructions=prompt_text(SUPPORT, version),
            text=json.dumps(
                {
                    "documents": knowledge.excerpts_for(message),
                    "earlier_messages": earlier,
                    "message": message,
                }
            ),
            prompt_version=version,
            max_output_tokens=get_setting("support.max_output_tokens"),
        )
    except AiUnavailable:  # includes AiPaused and AiBusy
        return None
    parsed = _parsed(reply.text)
    if parsed is None:
        return None
    longest = get_setting("support.max_reply_length")
    found = parsed.get("escalate")
    if isinstance(found, dict):
        handover = _handover(found)
        if handover is not None:
            return Turn(reply=_text(found.get("reply"), longest), handover=handover)
        return None
    text = _text(parsed.get("reply"), longest)
    return Turn(reply=text, handover=None) if text else None
