"""The minimal check of an uploaded CV: type, size, and whether it looks like a readable,
unprotected file of that type. Nothing is unpacked or decoded here.

File checks (BERA-112) replaces `check_cv_file` with the one real check, including the check
for scanned image-only PDFs; callers only use that name."""

import zipfile
from dataclasses import dataclass
from io import BytesIO

from platform_settings.service import get_setting

PDF_SIGNATURE = b"%PDF-"
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")  # an encrypted Word file is wrapped in this
BYTES_PER_MEGABYTE = 1024 * 1024
END_OF_PDF_WINDOW = 2048
DOCX_MAIN_PART = "word/document.xml"

WRONG_TYPE = "wrong_type"
EMPTY = "empty"
TOO_LARGE = "too_large"
DAMAGED = "damaged"
PASSWORD_PROTECTED = "password_protected"
TOO_MANY_FILES = "too_many_files"

DAMAGED_MESSAGE = "This file looks damaged and could not be read."
PASSWORD_MESSAGE = "This file is password protected. Remove the password and upload it again."


@dataclass(frozen=True)
class FileProblem:
    code: str
    message: str


def file_type_of(name):
    ending = str(name).rpartition(".")[2].lower() if "." in str(name) else ""
    return ending if ending in get_setting("uploads.allowed_file_types") else None


def type_names():
    return " or ".join(kind.upper() for kind in get_setting("uploads.allowed_file_types"))


def check_name_and_size(name, size):
    """The checks that need no file content, so a refused file is never read at all."""
    if file_type_of(name) is None:
        return FileProblem(WRONG_TYPE, f"Only {type_names()} files can be uploaded.")
    if size == 0:
        return FileProblem(EMPTY, "This file is empty.")
    largest = get_setting("uploads.max_file_size_mb")
    if size > largest * BYTES_PER_MEGABYTE:
        return FileProblem(TOO_LARGE, f"This file is larger than {largest} MB.")
    return None


def _check_pdf(data):
    if not data.startswith(PDF_SIGNATURE) or b"%%EOF" not in data[-END_OF_PDF_WINDOW:]:
        return FileProblem(DAMAGED, DAMAGED_MESSAGE)
    if b"/Encrypt" in data:
        return FileProblem(PASSWORD_PROTECTED, PASSWORD_MESSAGE)
    return None


def _check_docx(data):
    if data.startswith(OLE_SIGNATURE):
        return FileProblem(PASSWORD_PROTECTED, PASSWORD_MESSAGE)
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            if DOCX_MAIN_PART in archive.namelist():
                return None
    except zipfile.BadZipFile:
        pass
    return FileProblem(DAMAGED, DAMAGED_MESSAGE)


def check_cv_file(name, data):
    """None when the file is acceptable, otherwise why not, in words for the person."""
    if problem := check_name_and_size(name, len(data)):
        return problem
    return _check_pdf(data) if file_type_of(name) == "pdf" else _check_docx(data)
