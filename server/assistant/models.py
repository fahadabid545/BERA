from django.db import models

from core.models import CompanyOwnedModel
from core.protected_fields import EncryptedTextField


class AgentChat(CompanyOwnedModel):
    """One conversation with the company agent. Every person of the company sees and may continue
    or delete it. It holds no candidate details: only what was asked and answered (see
    `AgentMessage`), so a removed candidate leaves nothing behind in a chat."""

    title = models.CharField(max_length=200)
    # Who started it, only to tell "my chats" apart; a removed person leaves it empty.
    created_by = models.ForeignKey(
        "companies.CompanyUser", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["company", "-updated_at"], name="agentchat_company_time")]


class AgentMessage(CompanyOwnedModel):
    """One question or one answer. The text is encrypted, because a person may type a name into a
    question. An answer names candidates by reference (`[c_1a2b3c4d]`), and `candidate_ids` says
    which candidates it shows: their names and details are read from the live record each time
    the chat is opened, never copied here."""

    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    chat = models.ForeignKey(AgentChat, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    text = EncryptedTextField(purpose="agent_message.text")
    candidate_ids = models.JSONField(default=list)
    suggestions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["user", "assistant"]), name="agentmessage_role_known"
            )
        ]
