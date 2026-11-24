from django.utils import timezone
from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

from .models import NAME_COLUMN_LENGTH, NOTE_COLUMN_LENGTH, DataRequest


class _NoteMixin:
    def validate_note(self, value):
        if len(value) > get_setting("data_requests.max_note_length"):
            raise serializers.ValidationError("This note is too long.")
        return value


class NewDataRequestInput(_NoteMixin, StrictSerializer):
    company = serializers.IntegerField(min_value=1, max_value=2_000_000_000)
    kind = serializers.ChoiceField(choices=DataRequest.Kind.values)
    requested_by = SafeTextField(max_length=NAME_COLUMN_LENGTH)
    received_on = serializers.DateField()
    note = SafeTextField(
        max_length=NOTE_COLUMN_LENGTH, multiline=True, required=False, allow_blank=True
    )

    def validate_received_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("The received date cannot be in the future.")
        return value


class DataRequestChangeInput(_NoteMixin, StrictSerializer):
    status = serializers.ChoiceField(choices=DataRequest.Status.values, required=False)
    note = SafeTextField(
        max_length=NOTE_COLUMN_LENGTH, multiline=True, required=False, allow_blank=True
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError({"status": "Change the status or the note."})
        return attrs


class DataRequestListQuery(StrictSerializer):
    status = serializers.ChoiceField(choices=DataRequest.Status.values, required=False)
