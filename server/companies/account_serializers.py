from rest_framework import serializers

from core.passwords import PasswordTextField
from core.validation import SafeTextField, StrictSerializer

from .serializers import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, MAX_TOKEN_LENGTH


class ProfileSerializer(StrictSerializer):
    name = SafeTextField(max_length=MAX_NAME_LENGTH)


class EmailChangeSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)
    current_password = PasswordTextField()


class ConfirmEmailChangeSerializer(StrictSerializer):
    token = SafeTextField(max_length=MAX_TOKEN_LENGTH)


class CompanySettingsSerializer(StrictSerializer):
    name = SafeTextField(max_length=MAX_NAME_LENGTH, required=False)
    # None means "the platform default".
    retention_days = serializers.IntegerField(required=False, allow_null=True)
