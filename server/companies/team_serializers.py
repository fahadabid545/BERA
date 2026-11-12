from rest_framework import serializers

from core.passwords import PasswordField, PasswordTextField
from core.validation import SafeTextField, StrictSerializer

from .serializers import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, MAX_TOKEN_LENGTH


class InviteSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)


class AcceptInviteSerializer(StrictSerializer):
    token = SafeTextField(max_length=MAX_TOKEN_LENGTH)
    name = SafeTextField(max_length=MAX_NAME_LENGTH)
    password = PasswordField()
    confirm_password = PasswordTextField()

    def validate(self, values):
        if values["password"] != values["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "The passwords do not match."})
        return values


class TransferOwnershipSerializer(StrictSerializer):
    member_id = serializers.IntegerField(min_value=1)
    password = PasswordTextField()
