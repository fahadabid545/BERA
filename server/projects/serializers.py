from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting


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
