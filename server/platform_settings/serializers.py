from rest_framework import serializers

from adminusers.control_serializers import ReasonSerializer, StrictBoolean
from core.validation import SafeTextField, StrictSerializer

from .definitions import DEFINITIONS

MAX_MESSAGE_LENGTH = 500


class SettingsQuery(StrictSerializer):
    page = serializers.CharField(max_length=40, required=False)


class SaveSettings(StrictSerializer):
    values = serializers.DictField(child=serializers.JSONField(), allow_empty=False)

    def validate_values(self, value):
        if len(value) > len(DEFINITIONS):
            raise serializers.ValidationError("Too many settings.")
        return value


class MaintenanceInput(ReasonSerializer):
    enabled = StrictBoolean()
    message = SafeTextField(max_length=MAX_MESSAGE_LENGTH, required=False)
