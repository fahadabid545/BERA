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


def form_error(fields):
    """A form refused for the reasons in `fields` (field name to message)."""
    return AppError(
        "validation_error", "Please check the form and try again.", status_code=400, fields=fields
    )


# The only three answers a refusal may give. Each is built in one place so the text
# is identical for every cause (a missing token and an expired one, a record that
# does not exist and one that belongs to another company).
NOT_SIGNED_IN_MESSAGE = "You are not signed in."
NOT_ALLOWED_MESSAGE = "You do not have permission to do this."
NOT_FOUND_MESSAGE = "Not found."


def not_signed_in():
    return AppError("not_signed_in", NOT_SIGNED_IN_MESSAGE, status_code=401)


def not_allowed():
    return AppError("not_allowed", NOT_ALLOWED_MESSAGE, status_code=403)


def not_found():
    return AppError("not_found", NOT_FOUND_MESSAGE, status_code=404)
