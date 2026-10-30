"""The one way request input is checked before it is used.

Every request field gets a type, a length, a format and (where it has a fixed set of
choices) allowed values, by declaring a `StrictSerializer`:

    class NewProject(StrictSerializer):
        title = SafeTextField(max_length=200)
        notes = SafeTextField(max_length=2000, multiline=True, required=False)
        stage = serializers.ChoiceField(choices=["new", "shortlisted"])

Unknown extra fields are refused. Text is stored exactly as typed (never "cleaned" by
deleting parts of it) and is only ever sent back as JSON; the web app shows it as plain
text, so a `<script>` tag is displayed, never run. Database access goes through the ORM,
which sends values separately from the query.
"""

import re
import unicodedata
from collections.abc import Mapping

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from platform_settings.service import get_setting

# Control characters other than tab, new line and carriage return. NUL in particular
# makes PostgreSQL fail, which would otherwise surface as a server error.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# For single-line text, tabs and line breaks are not allowed either.
ANY_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Characters that are invalid in file names on common systems.
UNSAFE_FILE_NAME_CHARACTERS = re.compile(r'[<>:"|?*]')
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
FALLBACK_FILE_NAME = "file"
MAX_SHOWN_FIELD_NAME = 64


class SafeTextField(serializers.CharField):
    """Text with a required maximum length, no control characters, in one Unicode form."""

    default_error_messages = {
        "invalid": "Enter text.",
        "unsupported_characters": "Remove characters that are not supported.",
    }

    def __init__(self, *, max_length, multiline=False, **kwargs):
        self.multiline = multiline
        super().__init__(max_length=max_length, trim_whitespace=True, **kwargs)

    def to_internal_value(self, data):
        # CharField would quietly turn numbers into text; input must have the right type.
        if not isinstance(data, str):
            self.fail("invalid")
        value = unicodedata.normalize("NFC", super().to_internal_value(data))
        forbidden = CONTROL_CHARACTERS if self.multiline else ANY_CONTROL_CHARACTER
        if forbidden.search(value):
            self.fail("unsupported_characters")
        return value


class StrictSerializer(serializers.Serializer):
    """A serializer that refuses fields it does not declare."""

    def to_internal_value(self, data):
        errors = {}
        if isinstance(data, Mapping):
            accepted = {name for name, field in self.fields.items() if not field.read_only}
            for name in data:
                if name not in accepted:
                    errors[str(name)[:MAX_SHOWN_FIELD_NAME]] = ["This field is not allowed."]
        try:
            value = super().to_internal_value(data)
        except ValidationError as error:
            errors = {**error.detail, **errors}
        if errors:
            raise ValidationError(errors)
        return value


def safe_file_name(name):
    """A file name that can only ever name a file in the folder it is saved to.

    Folder parts, control characters and leading dots are removed and the length is
    limited (keeping the ending). Uploaded files should still be stored under a generated
    name; this is for the name shown to people.
    """
    last_part = re.split(r"[\\/]", str(name))[-1]
    cleaned = unicodedata.normalize("NFC", last_part)
    cleaned = CONTROL_CHARACTERS.sub("", cleaned)
    cleaned = UNSAFE_FILE_NAME_CHARACTERS.sub("_", cleaned).strip(" .")
    if not cleaned:
        return FALLBACK_FILE_NAME
    stem, dot, ending = cleaned.rpartition(".")
    if not dot:
        stem, ending = cleaned, ""
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    ending = f".{ending}" if dot else ""
    room = max(get_setting("requests.max_file_name_characters") - len(ending), 1)
    return stem[:room] + ending
