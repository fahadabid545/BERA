from rest_framework import serializers


class ChoiceSerializer(serializers.Serializer):
    kind = serializers.CharField(max_length=40)
    enabled = serializers.BooleanField()
