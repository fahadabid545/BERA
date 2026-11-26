"""The company agent's chats: asking, and the shared history.

Every person of the company sees every chat, may continue it, start a new one or delete one. An
incognito question is answered and kept nowhere: the browser sends the earlier messages along, as
the public website chat does.

What is saved is only the question and the answer (with references, not details), see
`models.AgentMessage`. The paid check is the one scoring uses (`plans.subscriptions.can_score`):
a company whose subscription or free trial does not allow AI work gets one plain message, and the
token allowance and the pause switch apply as they do to scoring.
"""

import uuid

from django.db import transaction

from core.errors import AppError
from core.scoping import get_in_company
from cvs.models import Candidate
from plans.limits import check_ai_allowed, prompt_kind
from plans.subscriptions import can_score
from platform_settings.service import get_setting

from . import agent, cards
from .allowance import require_allowance
from .models import AgentChat, AgentMessage
from .tools import candidate_reference

NEEDS_PLAN_CODE = "agent_needs_plan"
NEEDS_PLAN_MESSAGE = (
    "Buy our service to continue. If you have already bought it, try refreshing the page, or "
    "sign out and sign in again. If it still does not work, contact support."
)
CHAT_AND_INCOGNITO = "An incognito question cannot be added to a saved chat."
HISTORY_ONLY_INCOGNITO = "Only an incognito question brings its own earlier messages."


def require_access(company_id):
    if not can_score(company_id):
        raise AppError(
            NEEDS_PLAN_CODE,
            NEEDS_PLAN_MESSAGE,
            status_code=409,
            details={"prompt": prompt_kind(company_id)},
        )
    check_ai_allowed(company_id).raise_if_blocked()
    require_allowance(company_id)


def _known(candidate_ids):
    return {
        candidate_reference(uuid.UUID(str(item))): uuid.UUID(str(item)) for item in candidate_ids
    }


def _present(company_id, candidate_ids):
    """Only the candidates of this company that exist: the browser's list is never trusted."""
    return {
        str(pk)
        for pk in Candidate.objects.filter(company_id=company_id, pk__in=candidate_ids).values_list(
            "pk", flat=True
        )
    }


def _shown(message, cards_by_reference):
    return {
        "id": str(message.pk),
        "role": message.role,
        "text": message.text,
        "suggestions": message.suggestions,
        "created_at": message.created_at.isoformat(),
    }


def messages_of(chat):
    """The chat's messages, each with the cards of the candidates it names (as they are now)."""
    saved = list(chat.messages.all())
    ids = {item for message in saved for item in message.candidate_ids}
    live = cards.describe(chat.company_id, ids)
    return [
        {
            **_shown(message, live),
            "candidates": [
                live[reference]
                for reference in (
                    candidate_reference(uuid.UUID(item)) for item in message.candidate_ids
                )
                if reference in live
            ],
        }
        for message in saved
    ]


def list_chats(user):
    chats = AgentChat.objects.filter(company_id=user.company_id)[
        : get_setting("ask.max_chats_listed")
    ]
    return [
        {
            "id": str(chat.pk),
            "title": chat.title,
            "updated_at": chat.updated_at.isoformat(),
            "mine": chat.created_by_id == user.user_id,
        }
        for chat in chats
    ]


def get_chat(user, chat_id):
    return get_in_company(AgentChat.objects.all(), user.company_id, pk=chat_id)


def delete_chat(user, chat_id):
    get_chat(user, chat_id).delete()


def _recent(messages):
    most = get_setting("ask.max_history_messages")
    kept = messages[-most:] if most else []
    return [{"role": item["role"], "text": item["text"]} for item in kept]


def _reply_body(reply, company_id):
    live = cards.describe(company_id, reply.candidate_ids)
    return {
        "answer": reply.answer,
        "refused": reply.refused,
        "suggestions": reply.suggestions,
        "candidates": [
            live[reference]
            for reference in (candidate_reference(uuid.UUID(item)) for item in reply.candidate_ids)
            if reference in live
        ],
    }


def ask(user, question, *, chat_id=None, incognito=False, history=None, shown=None):
    """{"chat_id", "answer", "refused", "suggestions", "candidates"} for the question."""
    company_id = user.company_id
    if incognito and chat_id:
        raise AppError("agent_bad_request", CHAT_AND_INCOGNITO, status_code=400)
    if not incognito and (history or shown):
        raise AppError("agent_bad_request", HISTORY_ONLY_INCOGNITO, status_code=400)
    require_access(company_id)
    chat = get_chat(user, chat_id) if chat_id else None
    if chat:
        saved = [
            {"role": message.role, "text": message.text, "ids": message.candidate_ids}
            for message in chat.messages.all()
        ]
        earlier = _recent(saved)
        known = _known({item for message in saved for item in message["ids"]})
    else:
        earlier = _recent(history or [])
        known = _known(_present(company_id, shown or []))
    reply = agent.answer(company_id, question, earlier, known)
    body = {"chat_id": str(chat.pk) if chat else None, **_reply_body(reply, company_id)}
    if incognito:
        return body
    with transaction.atomic():
        if chat is None:
            chat = AgentChat.objects.create(
                company_id=company_id,
                created_by_id=user.user_id,
                title=question[: get_setting("ask.max_chat_title_length")],
            )
        for role, text, ids, suggestions in (
            (AgentMessage.Role.USER, question, [], []),
            (AgentMessage.Role.ASSISTANT, reply.answer, reply.candidate_ids, reply.suggestions),
        ):
            AgentMessage.objects.create(
                company_id=company_id,
                chat=chat,
                role=role,
                text=text,
                candidate_ids=ids,
                suggestions=suggestions,
            )
        chat.save(update_fields=["updated_at"])
    return {**body, "chat_id": str(chat.pk)}
