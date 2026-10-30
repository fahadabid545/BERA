from rest_framework import serializers

from core.passwords import PasswordField, PasswordTextField
from core.validation import SafeTextField, StrictSerializer

from .countries import COUNTRY_CODES, OTHER_COUNTRY

MAX_EMAIL_LENGTH = 254
MAX_NAME_LENGTH = 200
MAX_TOKEN_LENGTH = 200


class SignUpSerializer(StrictSerializer):
    company_name = SafeTextField(max_length=MAX_NAME_LENGTH)
    name = SafeTextField(max_length=MAX_NAME_LENGTH)
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)
    password = PasswordField()
    country = serializers.ChoiceField(
        choices=[*COUNTRY_CODES, OTHER_COUNTRY], default=OTHER_COUNTRY
    )
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, accepted):
        if accepted is not True:
            raise serializers.ValidationError("Accept the Terms and Privacy Policy to continue.")
        return accepted


class VerifyEmailSerializer(StrictSerializer):
    token = SafeTextField(max_length=MAX_TOKEN_LENGTH)


class ResendVerificationSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)


class ForgotPasswordSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)


class ResetPasswordSerializer(StrictSerializer):
    token = SafeTextField(max_length=MAX_TOKEN_LENGTH)
    password = PasswordField()
    confirm_password = PasswordTextField()

    def validate(self, values):
        if values["password"] != values["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "The passwords do not match."})
        return values
