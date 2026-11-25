from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer

WHOLE = {"min_value": 1, "max_value": 2_000_000_000}


class SettingsInput(StrictSerializer):
    enabled = serializers.BooleanField()
    model = SafeTextField(max_length=100, allow_blank=True)
    prompt_version = serializers.IntegerField(**WHOLE)
    visitor_questions_per_hour = serializers.IntegerField(**WHOLE)
    max_question_length = serializers.IntegerField(**WHOLE)
    max_answer_length = serializers.IntegerField(**WHOLE)
    daily_token_cap = serializers.IntegerField(**WHOLE)


class SwitchInput(StrictSerializer):
    enabled = serializers.BooleanField()


class DocumentFileInput(StrictSerializer):
    # An empty file is let through so the shared document check can refuse it in plain words.
    file = serializers.FileField(allow_empty_file=True)
