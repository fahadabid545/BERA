from rest_framework import serializers

from core.validation import StrictSerializer

MAX_EMAIL_LENGTH = 254
# A password is checked, not stored, so it only needs to be text; whether it is too long to be
# real is decided in login.py (where it counts as a wrong guess).
MAX_PASSWORD_LENGTH = 4096


class LoginSerializer(StrictSerializer):
    email = serializers.CharField(max_length=MAX_EMAIL_LENGTH)
    password = serializers.CharField(
        max_length=MAX_PASSWORD_LENGTH, trim_whitespace=False, write_only=True
    )

    def to_internal_value(self, data):
        # CharField would quietly turn numbers into text; input must have the right type.
        for name in ("email", "password"):
            if isinstance(data, dict) and name in data and not isinstance(data[name], str):
                raise serializers.ValidationError({name: ["Enter text."]})
        return super().to_internal_value(data)
