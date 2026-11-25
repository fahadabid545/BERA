import re

from rest_framework import serializers

from companies.countries import COUNTRY_CODES, OTHER_COUNTRY
from core.validation import StrictSerializer

from .invoices import KINDS

TAX_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9 .\-/]+$")
TAX_NUMBER_MAX_LENGTH = 40
BILLING_COUNTRIES = [code for code in COUNTRY_CODES if code != OTHER_COUNTRY]


class BillingDetailsSerializer(StrictSerializer):
    """Name and address are required; the tax number is optional and only checked lightly (its
    length and the characters a tax number uses), never against a country's format."""

    name = serializers.CharField(max_length=200)
    address_line1 = serializers.CharField(max_length=200)
    address_line2 = serializers.CharField(max_length=200, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country = serializers.ChoiceField(choices=BILLING_COUNTRIES)
    tax_number = serializers.CharField(
        max_length=TAX_NUMBER_MAX_LENGTH,
        required=False,
        allow_blank=True,
        error_messages={"max_length": "Use at most 40 characters."},
    )

    def validate_tax_number(self, value):
        value = value.strip()
        if value and not TAX_NUMBER_PATTERN.match(value):
            raise serializers.ValidationError("Use only letters, digits, spaces and . - /")
        return value

    def validate(self, attrs):
        for name in ("address_line2", "state", "postal_code", "tax_number"):
            attrs.setdefault(name, "")
        return attrs


class InvoiceLinkSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=KINDS, default=KINDS[0])
