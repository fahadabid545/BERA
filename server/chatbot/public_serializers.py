from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

ROLES = ("user", "assistant")
# A hard ceiling on what a browser may send, whatever the settings say; the service cuts each
# message to its own limit.
MOST_MESSAGES_SENT = 100
LONGEST_MESSAGE_SENT = 10_000


class EarlierMessage(StrictSerializer):
    role = serializers.ChoiceField(choices=ROLES)
    text = SafeTextField(max_length=LONGEST_MESSAGE_SENT, multiline=True, allow_blank=True)


class VisitorQuestion(StrictSerializer):
    question = SafeTextField(max_length=LONGEST_MESSAGE_SENT, multiline=True)
    history = EarlierMessage(many=True, required=False, default=list)

    def validate_history(self, value):
        if len(value) > MOST_MESSAGES_SENT:
            raise serializers.ValidationError("Too many earlier messages.")
        return value

    def validate_question(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Write a question.")
        limit = get_setting("chatbot.max_question_length")
        if len(value) > limit:
            raise serializers.ValidationError(f"Keep the question to {limit} characters.")
        return value
