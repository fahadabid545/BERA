from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

from .models import SupportTicket

TOO_LONG = "This is too long."
MESSAGE_COLUMN = 10_000


class _LimitedText:
    def validate_text(self, value):
        if len(value) > get_setting("support.max_message_length"):
            raise serializers.ValidationError(TOO_LONG)
        return value


class ChatMessageInput(_LimitedText, StrictSerializer):
    text = SafeTextField(max_length=MESSAGE_COLUMN, multiline=True)
    chat_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class TicketReplyInput(_LimitedText, StrictSerializer):
    text = SafeTextField(max_length=MESSAGE_COLUMN, multiline=True)


class AdminTicketInput(StrictSerializer):
    status = serializers.ChoiceField(choices=SupportTicket.Status.values, required=False)
    message = SafeTextField(max_length=MESSAGE_COLUMN, multiline=True, required=False)

    def validate_message(self, value):
        if len(value) > get_setting("support.max_message_length"):
            raise serializers.ValidationError(TOO_LONG)
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError({"status": "Write a message or change the status."})
        return attrs


class AdminTicketQuery(StrictSerializer):
    status = serializers.ChoiceField(choices=SupportTicket.Status.values, required=False)
    category = serializers.ChoiceField(choices=SupportTicket.Category.values, required=False)
