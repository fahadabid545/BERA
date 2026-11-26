"""The public website chatbot: a visitor asks a general question and gets an answer.

Isolated by construction:
- The only knowledge is the admin's public documents (`knowledge.py`). Nothing here imports or
  reads a company, project, candidate or CV table, and the call is made with no company.
- Stateless: the browser keeps the conversation and sends the last few messages with each
  question. Nothing the visitor wrote is stored and nothing is logged; the call record holds only
  the purpose, the model and the tokens (see `ai.client`).
- The visitor's words and the earlier messages are data for the AI to read, never instructions
  (the prompt says so, and they are sent apart from the prompt and the documents).
- Its own spend is capped per day (`chatbot.daily_token_cap`) and it can be switched off.
"""

import json

from django.db.models import Sum
from django.utils import timezone

from ai.client import AiPaused, AiUnavailable, call_ai
from ai.models import AiCall
from ai.prompt_versions import CHATBOT, current_number, prompt_text
from core.errors import AppError
from platform_settings.service import get_setting

from . import knowledge

PURPOSE = AiCall.Purpose.CHATBOT
# One message for every reason the chat cannot answer (switched off, over its daily cap, paused,
# an outage), so a visitor learns nothing about the platform's internals or spend.
UNAVAILABLE_MESSAGE = "The chat is not available right now. Please try again later."
UNUSABLE_MESSAGE = "We could not give a usable answer. Please ask in another way."


def is_on():
    return bool(get_setting("chatbot.enabled") and get_setting("chatbot.model"))


def widget_settings():
    """What the widget needs to know: whether it shows, and the limits it keeps to in the browser.
    Only numbers; nothing else about the platform."""
    if not is_on():
        return {"enabled": False}
    return {
        "enabled": True,
        "max_question_length": get_setting("chatbot.max_question_length"),
        "max_history_messages": get_setting("chatbot.max_history_messages"),
        "history_hours": get_setting("chatbot.history_hours"),
        "max_saved_chats": get_setting("chatbot.max_saved_chats"),
    }


def _tokens_used_today():
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    totals = AiCall.objects.filter(purpose=PURPOSE, created_at__gte=start).aggregate(
        tokens_in=Sum("tokens_in"), tokens_out=Sum("tokens_out")
    )
    return (totals["tokens_in"] or 0) + (totals["tokens_out"] or 0)


def _recent(history):
    """The last messages the visitor's browser sent, each cut to the length of a question or an
    answer: the browser is not trusted to keep them short."""
    limit = get_setting("chatbot.max_history_messages")
    longest = {
        "user": get_setting("chatbot.max_question_length"),
        "assistant": get_setting("chatbot.max_answer_length"),
    }
    kept = history[-limit:] if limit else []
    return [{"role": item["role"], "text": item["text"][: longest[item["role"]]]} for item in kept]


def _answer_from(text):
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        return None
    answer = parsed["answer"].strip()
    return answer[: get_setting("chatbot.max_answer_length")] or None


def answer(question, history):
    """{"answer"} for the question, or an AppError (503 whenever the chat cannot answer)."""
    if not is_on() or _tokens_used_today() >= get_setting("chatbot.daily_token_cap"):
        raise AppError("chatbot_unavailable", UNAVAILABLE_MESSAGE, status_code=503)
    version = current_number(CHATBOT)
    try:
        reply = call_ai(
            None,
            purpose=PURPOSE,
            model=get_setting("chatbot.model"),
            instructions=prompt_text(CHATBOT, version),
            text=json.dumps(
                {
                    "documents": knowledge.excerpts_for(question),
                    "earlier_messages": _recent(history),
                    "question": question,
                }
            ),
            prompt_version=version,
            max_output_tokens=get_setting("chatbot.max_output_tokens"),
        )
    except (AiPaused, AiUnavailable) as unavailable:
        raise AppError("chatbot_unavailable", UNAVAILABLE_MESSAGE, status_code=503) from unavailable
    understood = _answer_from(reply.text)
    if understood is None:
        raise AppError("chatbot_unusable", UNUSABLE_MESSAGE, status_code=502)
    return {"answer": understood}
