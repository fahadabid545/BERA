from decimal import Decimal

from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer

from .models import Plan
from .service import NOW, RENEWAL

MAX_REASON_LENGTH = 1000
# Prices are positive with two decimals; the other numbers are positive whole numbers.
PRICE_LIMIT = Decimal("99999999.99")


class WholeNumber(serializers.IntegerField):
    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=2_000_000_000, **kwargs)

    def to_internal_value(self, data):
        # 3.5, "3" and true are not whole numbers typed as numbers.
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class Price(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(
            max_digits=10,
            decimal_places=2,
            min_value=Decimal("0.01"),
            coerce_to_string=False,
            **kwargs,
        )

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, (int, str, float)):
            self.fail("invalid")
        # A float is read through its text, so 19.99 stays 19.99.
        return super().to_internal_value(str(data) if isinstance(data, float) else data)


class PlanFieldsSerializer(StrictSerializer):
    name = SafeTextField(max_length=100)
    description = SafeTextField(max_length=300, allow_blank=True)
    price_usd = Price(allow_null=True)
    price_pkr = Price(allow_null=True)
    cvs_per_month = WholeNumber(allow_null=True)
    cvs_per_project = WholeNumber(allow_null=True)
    max_projects = WholeNumber(allow_null=True)
    max_team_accounts = WholeNumber(allow_null=True)
    max_top_n = WholeNumber(allow_null=True)
    monthly_ai_token_cap = WholeNumber(allow_null=True)
    status = serializers.ChoiceField(choices=Plan.Status.values)
    display_order = serializers.IntegerField(min_value=0, max_value=1_000_000)


class CreatePlanSerializer(PlanFieldsSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = name == "name"


class ChangePlanSerializer(PlanFieldsSerializer):
    reason = SafeTextField(max_length=MAX_REASON_LENGTH, multiline=True)
    # Only matters for a plan with subscribers: wait for their renewal (the default) or now.
    apply = serializers.ChoiceField(choices=[NOW, RENEWAL], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = name == "reason"


class DeletePlanSerializer(StrictSerializer):
    reason = SafeTextField(max_length=MAX_REASON_LENGTH, multiline=True)
