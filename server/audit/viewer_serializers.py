from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer

from .events import KINDS

MAX_CURSOR_LENGTH = 100


class AuditFilters(StrictSerializer):
    person = SafeTextField(max_length=100, required=False)
    company = serializers.IntegerField(min_value=1, max_value=2_000_000_000, required=False)
    action = serializers.ChoiceField(choices=sorted(KINDS), required=False)
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)

    def validate(self, values):
        if (
            values.get("from_date")
            and values.get("to_date")
            and values["to_date"] < values["from_date"]
        ):
            raise serializers.ValidationError({"to_date": "The end date is before the start."})
        return values


class AuditPageQuery(AuditFilters):
    cursor = serializers.CharField(max_length=MAX_CURSOR_LENGTH, required=False)
