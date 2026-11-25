from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting


class QuestionInput(StrictSerializer):
    question = SafeTextField(max_length=5000, multiline=True)

    def validate_question(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Write a question.")
        limit = get_setting("ask.max_question_length")
        if len(value) > limit:
            raise serializers.ValidationError(f"Keep the question to {limit} characters.")
        return value
