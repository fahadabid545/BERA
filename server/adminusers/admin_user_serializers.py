from rest_framework import serializers

from companies.serializers import MAX_TOKEN_LENGTH
from core.passwords import PasswordField, PasswordTextField
from core.validation import SafeTextField, StrictSerializer

from .control_serializers import ReasonSerializer
from .models import AdminUser

MAX_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 254


class InviteAdminSerializer(ReasonSerializer):
    name = SafeTextField(max_length=MAX_NAME_LENGTH)
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)
    role = serializers.ChoiceField(choices=AdminUser.Role.values)


class ChangeRoleSerializer(ReasonSerializer):
    role = serializers.ChoiceField(choices=AdminUser.Role.values)


class ChangeStatusSerializer(ReasonSerializer):
    # "removed" is not offered here: a disabled admin can be enabled again.
    status = serializers.ChoiceField(choices=[AdminUser.Status.ACTIVE, AdminUser.Status.BLOCKED])


class AcceptAdminInviteSerializer(StrictSerializer):
    token = SafeTextField(max_length=MAX_TOKEN_LENGTH)
    password = PasswordField()
    confirm_password = PasswordTextField()

    def validate(self, values):
        if values["password"] != values["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "The passwords do not match."})
        return values
