from decimal import Decimal

from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer

MAX_REASON_LENGTH = 1000
MAX_NAME_LENGTH = 100


class ModelPrice(serializers.DecimalField):
    """A price per million tokens: not negative, at most four decimals."""

    def __init__(self, **kwargs):
        super().__init__(
            max_digits=12,
            decimal_places=4,
            min_value=Decimal(0),
            coerce_to_string=False,
            **kwargs,
        )

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, (int, str, float)):
            self.fail("invalid")
        return super().to_internal_value(str(data) if isinstance(data, float) else data)


class AddModelSerializer(StrictSerializer):
    name = SafeTextField(max_length=MAX_NAME_LENGTH)
    input_price_per_million = ModelPrice()
    output_price_per_million = ModelPrice()
    enabled = serializers.BooleanField(required=False, default=True)


class ChangeModelSerializer(StrictSerializer):
    reason = SafeTextField(max_length=MAX_REASON_LENGTH)
    input_price_per_million = ModelPrice(required=False)
    output_price_per_million = ModelPrice(required=False)
    enabled = serializers.BooleanField(required=False)
    replacement = serializers.IntegerField(required=False, min_value=1)


class SelectModelsSerializer(StrictSerializer):
    reason = SafeTextField(max_length=MAX_REASON_LENGTH)
    reading_model = serializers.IntegerField(min_value=1)
    scoring_model = serializers.IntegerField(min_value=1)
