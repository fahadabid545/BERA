"""The one way errors are reported across the project.

Every error has a stable machine-readable `code`, a plain-language `message`
and optional non-sensitive `details`. Form mistakes add `fields` (field name to
message) and unexpected failures add a `reference` that is also in the log.
API responses use the shape `{"error": {"code": ..., "message": ..., ...}}`.

Everything in an AppError is shown to the user, so write it for them: no file
paths, database messages or internal names.
"""


class AppError(Exception):
    status_code = 400

    def __init__(
        self, code, message, details=None, status_code=None, *, fields=None, reference=None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.fields = fields
        self.reference = reference
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self):
        body = {"code": self.code, "message": self.message}
        if self.details is not None:
            body["details"] = self.details
        if self.fields is not None:
            body["fields"] = self.fields
        if self.reference is not None:
            body["reference"] = self.reference
        return body


class ConfigurationError(AppError):
    """The app is set up wrongly (e.g. a required secret is missing)."""

    status_code = 500

    def __init__(self, message, details=None):
        super().__init__("configuration_error", message, details)
