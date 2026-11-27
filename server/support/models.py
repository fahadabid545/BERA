from django.db import models
from django.db.models import Q

from core.models import CompanyOwnedModel
from core.protected_fields import EncryptedTextField

TITLE_COLUMN_LENGTH = 200


class SupportTicket(CompanyOwnedModel):
    """One problem handed to the support team: written by the support agent in a fixed shape (a
    title, a category and four short parts), then worked on by an admin. Everything the person
    wrote is company data, so it is stored encrypted and never written to a log, an audit entry
    or an email."""

    class Category(models.TextChoices):
        BUG = "bug"
        BILLING = "billing"
        HOW_TO = "how_to"
        ACCOUNT = "account"
        OTHER = "other"

    class Status(models.TextChoices):
        OPEN = "open"
        WORKING = "working"
        NEEDS_REPLY = "needs_reply"  # the team asked the person something
        COMPLETED = "completed"
        CLOSED = "closed"

    # Shown as SUP-<number>; a counter, because people quote it in conversation.
    number = models.PositiveIntegerField(unique=True)
    user = models.ForeignKey("companies.CompanyUser", on_delete=models.PROTECT, related_name="+")
    category = models.CharField(max_length=10, choices=Category.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    title = EncryptedTextField(purpose="support_ticket.title")
    summary = EncryptedTextField(purpose="support_ticket.summary")
    what_happened = EncryptedTextField(purpose="support_ticket.what_happened")
    expected = EncryptedTextField(purpose="support_ticket.expected")
    steps = EncryptedTextField(purpose="support_ticket.steps")
    # The admin who first picked it up; empty until then or when that admin is removed.
    handled_by = models.ForeignKey(
        "adminusers.AdminUser", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["status", "-updated_at"], name="ticket_status_newest")]
        constraints = [
            models.CheckConstraint(
                condition=Q(category__in=["bug", "billing", "how_to", "account", "other"]),
                name="ticket_category_is_known",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["open", "working", "needs_reply", "completed", "closed"]),
                name="ticket_status_is_known",
            ),
        ]


class TicketMessage(CompanyOwnedModel):
    """One line of a ticket's conversation: the person, the support team, or the system noting a
    change of status."""

    class Author(models.TextChoices):
        USER = "user"
        ADMIN = "admin"
        SYSTEM = "system"

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.CharField(max_length=10, choices=Author.choices)
    text = EncryptedTextField(purpose="support_ticket_message.text")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(author__in=["user", "admin", "system"]),
                name="ticketmessage_author_is_known",
            )
        ]


class SupportChat(CompanyOwnedModel):
    """One person's conversation with the support agent. Private to that person. Once the agent
    hands the problem to the team, the chat points at the ticket and is closed."""

    user = models.ForeignKey("companies.CompanyUser", on_delete=models.PROTECT, related_name="+")
    ticket = models.OneToOneField(
        SupportTicket, null=True, on_delete=models.SET_NULL, related_name="chat"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SupportChatMessage(CompanyOwnedModel):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    chat = models.ForeignKey(SupportChat, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    text = EncryptedTextField(purpose="support_chat_message.text")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=["user", "assistant"]), name="supportchatmessage_role_known"
            )
        ]
