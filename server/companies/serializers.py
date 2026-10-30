from rest_framework import serializers

from core.passwords import PasswordField
from core.validation import SafeTextField, StrictSerializer

from .countries import COUNTRY_CODES, OTHER_COUNTRY

MAX_EMAIL_LENGTH = 254
MAX_NAME_LENGTH = 200


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
