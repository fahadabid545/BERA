from rest_framework import serializers

from core.validation import SafeTextField, StrictSerializer
from platform_settings.service import get_setting

EMAIL_MAXIMUM = 254  # the longest address that exists
TOKEN_MAXIMUM = 500
HONEYPOT_MAXIMUM = 1000


class ContactInput(StrictSerializer):
    # The limits are platform settings, read when the request arrives.
    name = SafeTextField(max_length=200)
    email = serializers.EmailField(max_length=EMAIL_MAXIMUM)
    message = SafeTextField(max_length=10000, multiline=True)
    # The two spam traps: `website` is hidden from people and stays empty; `form_token` is the
    # signed moment the form was opened. Neither is ever reported back as a mistake, so a bot
    # learns nothing from the answer.
    website = serializers.CharField(required=False, allow_blank=True, max_length=HONEYPOT_MAXIMUM)
    form_token = serializers.CharField(required=False, allow_blank=True, max_length=TOKEN_MAXIMUM)

    def validate_name(self, value):
        if len(value) > get_setting("contact.max_name_length"):
            raise serializers.ValidationError("This name is too long.")
        return value

    def validate_message(self, value):
        if len(value) > get_setting("contact.max_message_length"):
            raise serializers.ValidationError("This message is too long.")
        return value
