from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

from .models import NOTE_COLUMN_LENGTH, PAGE_COLUMN_LENGTH, Feedback

COMPANY_PAGE_PREFIX = "/company"
TOO_LONG = "This is too long."


class NewFeedbackInput(StrictSerializer):
    kind = serializers.ChoiceField(choices=Feedback.Kind.values)
    message = SafeTextField(max_length=5000, multiline=True)
    page = SafeTextField(max_length=PAGE_COLUMN_LENGTH)

    def validate_message(self, value):
        if len(value) > get_setting("feedback.max_message_length"):
            raise serializers.ValidationError(TOO_LONG)
        return value

    def validate_page(self, value):
        # Only a page of the company panel, never an address with a query or a fragment (those
        # can carry tokens).
        if not value.startswith(COMPANY_PAGE_PREFIX) or any(mark in value for mark in "?#"):
            raise serializers.ValidationError("Enter a page address of the company panel.")
        return value


class FeedbackChangeInput(StrictSerializer):
    status = serializers.ChoiceField(choices=Feedback.Status.values, required=False)
    note = SafeTextField(
        max_length=NOTE_COLUMN_LENGTH, multiline=True, required=False, allow_blank=True
    )

    def validate_note(self, value):
        if len(value) > get_setting("feedback.max_note_length"):
            raise serializers.ValidationError(TOO_LONG)
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError({"status": "Change the status or the note."})
        return attrs


class FeedbackListQuery(StrictSerializer):
    status = serializers.ChoiceField(choices=Feedback.Status.values, required=False)
    kind = serializers.ChoiceField(choices=Feedback.Kind.values, required=False)
    since = serializers.DateField(required=False)
    until = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get("since") and attrs.get("until") and attrs["since"] > attrs["until"]:
            raise serializers.ValidationError({"until": "The end date is before the start date."})
        return attrs
