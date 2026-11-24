from django.utils import timezone
from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

from .models import MESSAGE_COLUMN_LENGTH, Announcement

MAX_COMPANIES_PER_BANNER = 5000  # a sanity bound on the request, not a platform rule


class AnnouncementInput(StrictSerializer):
    message = SafeTextField(max_length=MESSAGE_COLUMN_LENGTH)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    target = serializers.ChoiceField(choices=Announcement.Target.values)
    plan = serializers.IntegerField(min_value=1, max_value=2_000_000_000, required=False)
    companies = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=2_000_000_000),
        max_length=MAX_COMPANIES_PER_BANNER,
        required=False,
    )
    # Only a new banner must still be on in the future; editing may end one early.
    must_end_in_future = False

    def validate_message(self, value):
        if len(value) > get_setting("announcements.max_message_length"):
            raise serializers.ValidationError("This message is too long.")
        return value

    def validate(self, attrs):
        problems = {}
        if attrs["ends_at"] <= attrs["starts_at"]:
            problems["ends_at"] = "The end must be after the start."
        elif self.must_end_in_future and attrs["ends_at"] <= timezone.now():
            problems["ends_at"] = "The end must be in the future."
        target = attrs["target"]
        if target == Announcement.Target.PLAN and "plan" not in attrs:
            problems["plan"] = "Choose a plan."
        if target != Announcement.Target.PLAN and "plan" in attrs:
            problems["plan"] = "A plan is only used when the target is a plan."
        if target == Announcement.Target.COMPANIES and not attrs.get("companies"):
            problems["companies"] = "Choose at least one company."
        if target != Announcement.Target.COMPANIES and "companies" in attrs:
            problems["companies"] = "Companies are only used when the target is chosen companies."
        if problems:
            raise serializers.ValidationError(problems)
        return attrs


class NewAnnouncementInput(AnnouncementInput):
    must_end_in_future = True
