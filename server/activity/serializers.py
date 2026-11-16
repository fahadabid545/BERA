from rest_framework import serializers

from core.validation import StrictSerializer


class ListQuerySerializer(StrictSerializer):
    before = serializers.DateTimeField(required=False)
    actor = serializers.IntegerField(required=False)
    since = serializers.DateField(required=False)  # first day, inclusive (UTC)
    until = serializers.DateField(required=False)  # last day, inclusive (UTC)

    def validate(self, attrs):
        since, until = attrs.get("since"), attrs.get("until")
        if since and until and since > until:
            raise serializers.ValidationError({"until": "The last day cannot be before the first."})
        return attrs
