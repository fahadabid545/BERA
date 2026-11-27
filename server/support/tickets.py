"""Support tickets: made from a chat with the support agent, read by the person who opened them
(and by the company's owner), and worked on by the admins.

A person answers a question of the team and sees the status. An admin reads the ticket, asks the
person for more, works on it, and sets its status: open, working, needs a reply, completed or
closed. A change of status is a line in the conversation and an audit entry; nothing the person
wrote goes to a log, an audit entry or an email.
"""

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from audit.service import record
from core.errors import AppError, not_found
from platform_settings.service import get_setting

from .models import SupportTicket, TicketMessage

Status = SupportTicket.Status
Author = TicketMessage.Author
CLOSED_CODE = "ticket_closed"
CLOSED_MESSAGE = "This ticket is closed. Please open a new one."
STATUS_WORDS = {
    Status.OPEN: "Open",
    Status.WORKING: "Working on it",
    Status.NEEDS_REPLY: "Waiting for your reply",
    Status.COMPLETED: "Completed",
    Status.CLOSED: "Closed",
}
NUMBER_TRIES = 5


def _next_number():
    return (SupportTicket.objects.aggregate(last=Max("number"))["last"] or 0) + 1


def create_from_chat(chat, handover):
    """The ticket for a chat, written in the agent's fixed shape; the chat now points at it."""
    for attempt in range(NUMBER_TRIES):
        try:
            with transaction.atomic():
                ticket = SupportTicket.objects.create(
                    company_id=chat.company_id,
                    user_id=chat.user_id,
                    number=_next_number(),
                    category=handover.category,
                    title=handover.title,
                    summary=handover.summary,
                    what_happened=handover.what_happened,
                    expected=handover.expected,
                    steps=handover.steps,
                )
        except IntegrityError:  # another ticket took the number at the same moment
            if attempt == NUMBER_TRIES - 1:
                raise
            continue
        break
    chat.ticket = ticket
    chat.save(update_fields=["ticket"])
    return ticket


def summary_of(ticket):
    return {
        "id": str(ticket.pk),
        "number": ticket.number,
        "title": ticket.title,
        "category": ticket.category,
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
    }


def detail_of(ticket, *, for_admin=False):
    return {
        **summary_of(ticket),
        "summary": ticket.summary,
        "what_happened": ticket.what_happened,
        "expected": ticket.expected,
        "steps": ticket.steps,
        "messages": [
            {
                "id": str(item.pk),
                "author": item.author,
                "text": item.text,
                "created_at": item.created_at.isoformat(),
            }
            for item in ticket.messages.all()
        ],
        **(
            {
                "company_id": ticket.company_id,
                "company": ticket.company.name,
                "user": ticket.user.name,
                "handled_by": ticket.handled_by.name if ticket.handled_by_id else None,
            }
            if for_admin
            else {}
        ),
    }


# ---- the company side ----


def visible_to(user):
    """The tickets a person may read: their own, and all of the company's for its owner."""
    found = SupportTicket.objects.filter(company_id=user.company_id)
    return found if user.role == "owner" else found.filter(user_id=user.user_id)


def list_for(user):
    found = visible_to(user).order_by("-updated_at", "-number")
    return [summary_of(item) for item in found[: get_setting("support.ticket_list_limit")]]


def get_for(user, ticket_id):
    found = visible_to(user).filter(pk=ticket_id).first()
    if found is None:
        raise not_found()
    return found


def add_message(ticket, author, text):
    return TicketMessage.objects.create(
        company_id=ticket.company_id, ticket=ticket, author=author, text=text
    )


def person_replies(user, ticket_id, text):
    """The person answers the team (or adds to the ticket). A reply to a question puts the ticket
    back in the team's hands; a completed ticket is open again."""
    with transaction.atomic():
        ticket = get_for(user, ticket_id)
        ticket = SupportTicket.objects.select_for_update().get(pk=ticket.pk)
        if ticket.status == Status.CLOSED:
            raise AppError(CLOSED_CODE, CLOSED_MESSAGE, status_code=409)
        add_message(ticket, Author.USER, text)
        if ticket.status in (Status.NEEDS_REPLY, Status.COMPLETED):
            ticket.status = Status.WORKING if ticket.status == Status.NEEDS_REPLY else Status.OPEN
        ticket.save(update_fields=["status", "updated_at"])
    return ticket


# ---- the admin side ----


def list_for_admin(filters):
    found = SupportTicket.objects.select_related("company", "user").all()
    if filters.get("status"):
        found = found.filter(status=filters["status"])
    else:
        found = found.exclude(status__in=(Status.COMPLETED, Status.CLOSED))
    if filters.get("category"):
        found = found.filter(category=filters["category"])
    limit = get_setting("support.admin_list_limit")
    return {
        "total": found.count(),
        "items": [
            {
                **summary_of(item),
                "company_id": item.company_id,
                "company": item.company.name,
                "user": item.user.name,
            }
            for item in found.order_by("-updated_at", "-number")[:limit]
        ],
        "open_count": SupportTicket.objects.filter(status=Status.OPEN).count(),
    }


def get_for_admin(ticket_id):
    found = (
        SupportTicket.objects.select_related("company", "user", "handled_by")
        .filter(pk=ticket_id)
        .first()
    )
    if found is None:
        raise not_found()
    return found


def admin_updates(admin, ticket_id, values):
    """An admin's message to the person and/or a new status. Asking the person something with no
    status given leaves the ticket "waiting for your reply"; a status change is recorded."""
    with transaction.atomic():
        ticket = SupportTicket.objects.select_for_update().filter(pk=ticket_id).first()
        if ticket is None:
            raise not_found()
        old_status = ticket.status
        text = values.get("message")
        status = values.get("status") or (Status.NEEDS_REPLY if text else old_status)
        if text:
            add_message(ticket, Author.ADMIN, text)
        if ticket.handled_by_id is None:
            ticket.handled_by = admin
        if status != old_status:
            ticket.status = status
            ticket.closed_at = timezone.now() if status == Status.CLOSED else None
            add_message(ticket, Author.SYSTEM, STATUS_WORDS[status])
            record(
                "admin.support_ticket_status_changed",
                actor=admin,
                company_id=ticket.company_id,
                details={
                    "ticket_number": ticket.number,
                    "old_status": old_status,
                    "new_status": status,
                },
            )
        ticket.save(update_fields=["status", "handled_by", "closed_at", "updated_at"])
    return get_for_admin(ticket.pk)
