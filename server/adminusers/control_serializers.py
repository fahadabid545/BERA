from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from plans.serializers import MAX_REASON_LENGTH, WholeNumber


class ReasonSerializer(StrictSerializer):
    reason = SafeTextField(max_length=MAX_REASON_LENGTH, multiline=True)


class SetLimitSerializer(ReasonSerializer):
    value = WholeNumber()


class GrantFreeSerializer(ReasonSerializer):
    plan_id = serializers.IntegerField(min_value=1)
    period_end = serializers.DateTimeField()

    def validate_period_end(self, value):
        if value <= timezone.now() + timedelta(minutes=1):
            raise serializers.ValidationError("The free period must end in the future.")
        return value


class StrictBoolean(serializers.BooleanField):
    """Only true or false as typed: "yes" and 1 are not an answer to a security question."""

    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail("invalid", input=data)
        return data


class CompanyUserTwoStepSerializer(ReasonSerializer):
    identity_checked = StrictBoolean()
