"""A person's conversation with the support agent, up to the moment a ticket is made.

The person writes; the agent answers, asks, or hands the problem to the team. A hand-over makes a
ticket (`tickets.create_from_chat`) and closes the chat. The person can always reach the team: when
the agent cannot answer (AI paused, unavailable, an unusable answer) or the chat has gone on for
`support.max_user_messages_per_chat` messages, the team gets the conversation as it is.
"""

from django.db import transaction

from core.errors import AppError
from core.scoping import get_in_company
from platform_settings.service import get_setting

from . import agent, tickets
from .models import SupportChat, SupportChatMessage

ALREADY_HANDED_CODE = "support_chat_closed"
ALREADY_HANDED_MESSAGE = (
    "This chat was already sent to the support team. You can follow it under your tickets."
)
TEAM_TOLD = "We have sent this to the support team. You can follow it under your tickets."
FALLBACK_TITLE = "Question for the support team"


def _earlier(chat):
    kept = list(chat.messages.all())[-get_setting("support.history_messages") :]
    return [{"role": item.role, "text": item.text} for item in kept]


def _fallback_handover(chat):
    """A hand-over made from what the person wrote, when the agent could not make one."""
    written = [item.text for item in chat.messages.all() if item.role == "user"]
    longest = get_setting("support.max_field_length")
    return agent.Handover(
        title=(written[0] if written else FALLBACK_TITLE)[
            : get_setting("support.max_title_length")
        ],
        category="other",
        summary=written[0][:longest] if written else "",
        what_happened="\n\n".join(written)[:longest],
        expected="",
        steps="",
    )


def get_chat(user, chat_id):
    """The person's own chat; another person's, even in the same company, is "not found"."""
    return get_in_company(
        SupportChat.objects.filter(user_id=user.user_id), user.company_id, pk=chat_id
    )


def messages_of(chat):
    return [
        {"id": str(item.pk), "role": item.role, "text": item.text,
         "created_at": item.created_at.isoformat()}
        for item in chat.messages.all()
    ]  # fmt: skip


def send(user, text, chat_id=None):
    """{"chat_id", "reply", "ticket"} for a message: the agent's answer, or the ticket it made."""
    chat = (
        get_chat(user, chat_id)
        if chat_id
        else SupportChat.objects.create(company_id=user.company_id, user_id=user.user_id)
    )
    if chat.ticket_id:
        raise AppError(ALREADY_HANDED_CODE, ALREADY_HANDED_MESSAGE, status_code=409)
    SupportChatMessage.objects.create(
        company_id=user.company_id, chat=chat, role=SupportChatMessage.Role.USER, text=text
    )
    written = chat.messages.filter(role=SupportChatMessage.Role.USER).count()
    turn = None
    if written <= get_setting("support.max_user_messages_per_chat"):
        turn = agent.next_turn(user.company_id, text, _earlier(chat)[:-1])
    if turn is None:
        handover, reply = _fallback_handover(chat), TEAM_TOLD
    else:
        handover = turn.handover
        reply = turn.reply or (TEAM_TOLD if handover else "")
    with transaction.atomic():
        SupportChatMessage.objects.create(
            company_id=user.company_id,
            chat=chat,
            role=SupportChatMessage.Role.ASSISTANT,
            text=reply,
        )
        ticket = tickets.create_from_chat(chat, handover) if handover else None
        chat.save(update_fields=["updated_at"])
    return {
        "chat_id": str(chat.pk),
        "reply": reply,
        "ticket": tickets.detail_of(ticket) if ticket else None,
    }
