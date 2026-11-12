from rest_framework import serializers

from core.validation import StrictSerializer


class ListQuerySerializer(StrictSerializer):
    before = serializers.DateTimeField(required=False)
