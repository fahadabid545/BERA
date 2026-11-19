from rest_framework import serializers

from core.validation import StrictSerializer

from .serializers import MAX_NAME_LENGTH, MAX_TOKEN_LENGTH


class DeleteCompanySerializer(StrictSerializer):
    confirm_name = serializers.CharField(max_length=MAX_NAME_LENGTH, trim_whitespace=False)
    acknowledge_subscription = serializers.BooleanField(required=False, default=False)


class UndoDeletionSerializer(StrictSerializer):
    token = serializers.CharField(max_length=MAX_TOKEN_LENGTH)
