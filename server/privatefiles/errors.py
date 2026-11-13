from core.errors import AppError


class StorageUnavailable(AppError):
    """The file store could not be reached, even after trying again."""

    def __init__(self):
        super().__init__(
            "storage_unavailable",
            "File storage is not reachable right now. Please try again in a moment.",
            status_code=503,
        )


class StorageError(Exception):
    """One failed attempt by a backend; worth trying again. Never shown to people."""


class StoredFileMissing(Exception):
    """The file is not in the store (no point trying again)."""


class InvalidLink(AppError):
    def __init__(self):
        super().__init__("link_invalid", "This link has expired or is not valid.", status_code=403)
