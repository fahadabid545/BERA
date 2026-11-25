from django.utils import timezone
from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer

from .models import NAME_COLUMN_LENGTH
from .scopes import SCOPES


class NewKeyInput(StrictSerializer):
    name = SafeTextField(max_length=NAME_COLUMN_LENGTH)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=SCOPES), min_length=1, max_length=len(SCOPES)
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_scopes(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Each scope may be chosen once.")
        return value

    def validate_expires_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("The expiry must be in the future.")
        return value
