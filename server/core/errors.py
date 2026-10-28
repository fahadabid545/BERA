"""The one way errors are reported across the project.

Every error has a stable machine-readable `code`, a human-readable `message`
and optional non-sensitive `details`. API responses use the shape
`{"error": {"code": ..., "message": ..., "details": ...}}`.
"""


class AppError(Exception):
    status_code = 400

    def __init__(self, code, message, details=None, status_code=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self):
        body = {"code": self.code, "message": self.message}
        if self.details is not None:
            body["details"] = self.details
        return body


class ConfigurationError(AppError):
    """The app is set up wrongly (e.g. a required secret is missing)."""

    status_code = 500

    def __init__(self, message, details=None):
        super().__init__("configuration_error", message, details)
