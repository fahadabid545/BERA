from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

from .listing import DEFAULT_SORT, DEFAULT_STATUS, SORTS, STATUS_FILTERS


class CreateProjectSerializer(StrictSerializer):
    """Limits are read when the serializer is made, so a changed setting applies at once."""

    # Warnings (a short description, a repeated title) do not refuse the request; the person
    # confirms them and sends it again with this set.
    acknowledge_warnings = serializers.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"] = SafeTextField(max_length=get_setting("projects.title_max_length"))
        self.fields["job_description"] = SafeTextField(
            max_length=get_setting("projects.description_max_length"), multiline=True
        )


class ListProjectsSerializer(StrictSerializer):
    """The query string of the list. Unknown or invalid values are refused, not ignored."""

    search = SafeTextField(max_length=200, required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=STATUS_FILTERS, default=DEFAULT_STATUS)
    sort = serializers.ChoiceField(choices=list(SORTS), default=DEFAULT_SORT)
    page = serializers.IntegerField(min_value=1, max_value=1_000_000, default=1)


class EditProjectSerializer(StrictSerializer):
    """Only what is sent changes; the limits are the same as when creating."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"] = SafeTextField(
            max_length=get_setting("projects.title_max_length"), required=False
        )
        self.fields["job_description"] = SafeTextField(
            max_length=get_setting("projects.description_max_length"),
            multiline=True,
            required=False,
        )


class DeleteProjectSerializer(StrictSerializer):
    confirm_title = SafeTextField(max_length=1000)


class RequirementSerializer(StrictSerializer):
    id = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(choices=["must", "nice"])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"] = SafeTextField(max_length=get_setting("requirements.max_length"))
        self.fields["weight"] = serializers.IntegerField(
            required=False, min_value=1, max_value=get_setting("requirements.weight_max")
        )

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if "id" in value:
            value["id"] = str(value["id"])
        return value


class SaveRequirementsSerializer(StrictSerializer):
    requirements = serializers.ListField(child=serializers.DictField(), max_length=1000)
    acknowledge_rescoring = serializers.BooleanField(default=False)

    def validate_requirements(self, items):
        checked = []
        for number, item in enumerate(items, start=1):
            single = RequirementSerializer(data=item)
            if not single.is_valid():
                field, messages = next(iter(single.errors.items()))
                raise serializers.ValidationError(f"Requirement {number}, {field}: {messages[0]}")
            checked.append(single.validated_data)
        return checked


class ScoringSettingsSerializer(StrictSerializer):
    """Every value is sent every time. Whether the combination is possible, and the plan's
    top-N cap, are checked when saving, with one clear message each."""

    must_weight_percent = serializers.IntegerField()
    nice_weight_percent = serializers.IntegerField()
    recommendation_threshold = serializers.IntegerField()
    top_n = serializers.IntegerField(max_value=1_000_000)
    cap_on_missing_must_have = serializers.BooleanField()


class TypedWholeNumber(serializers.IntegerField):
    """A number typed as a number: not "5", not 5.5, not true."""

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class FactorSerializer(StrictSerializer):
    enabled = serializers.BooleanField()
    weight = TypedWholeNumber(min_value=-1_000_000, max_value=1_000_000)


class FactorSettingsSerializer(StrictSerializer):
    """Every value is sent every time; what is possible is checked when saving."""

    required_years = TypedWholeNumber(allow_null=True, min_value=-1, max_value=1_000_000)
    required_education = serializers.CharField(allow_null=True, max_length=20)
    seniority = serializers.CharField(allow_null=True, max_length=20)
    factors = serializers.DictField(child=FactorSerializer())

    def validate_factors(self, value):
        if len(value) > 50:
            raise serializers.ValidationError("Too many factors.")
        return {name: dict(setting) for name, setting in value.items()}
