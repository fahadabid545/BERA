from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

MOST_SENT = 100  # a ceiling on what a browser may send, whatever the settings say
LONGEST_MESSAGE_SENT = 10_000


class EarlierMessage(StrictSerializer):
    role = serializers.ChoiceField(choices=("user", "assistant"))
    text = SafeTextField(max_length=LONGEST_MESSAGE_SENT, multiline=True, allow_blank=True)


class QuestionInput(StrictSerializer):
    question = SafeTextField(max_length=5000, multiline=True)
    chat_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    incognito = serializers.BooleanField(required=False, default=False)
    history = EarlierMessage(many=True, required=False, default=list)
    shown = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=MOST_SENT
    )

    def validate_question(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Write a question.")
        limit = get_setting("ask.max_question_length")
        if len(value) > limit:
            raise serializers.ValidationError(f"Keep the question to {limit} characters.")
        return value

    def validate_history(self, value):
        if len(value) > MOST_SENT:
            raise serializers.ValidationError("Too many earlier messages.")
        return value
