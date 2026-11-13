"""The one check every uploaded CV goes through: `check_cv_file`.

It decides the real type of the file from its content (a renamed file is refused), then checks
that the file is readable, not protected, free of macros, scripts and embedded content, and
reports its page count. Nothing is ever run or opened as a program: files are only read as
data, and archives are measured from their headers before anything is unpacked.

`cvs/service.py` calls `check_cv_file` and nothing else here, so the rules live in one place."""

from dataclasses import dataclass, field

from platform_settings.service import get_setting

BYTES_PER_MEGABYTE = 1024 * 1024

WRONG_TYPE = "wrong_type"
TYPE_MISMATCH = "type_mismatch"
EMPTY = "empty"
TOO_LARGE = "too_large"
DAMAGED = "damaged"
PASSWORD_PROTECTED = "password_protected"
SCANNED_IMAGE = "scanned_image"
ACTIVE_CONTENT = "active_content"
TOO_MANY_FILES = "too_many_files"
MORE_PAGES_THAN_READ = "more_pages_than_read"

DAMAGED_MESSAGE = "This file looks damaged and could not be read."
PASSWORD_MESSAGE = "This file is password protected. Remove the password and upload it again."
MISMATCH_MESSAGE = (
    "This file is not really a {kind} file, whatever its name says. "
    "Upload the original PDF or Word file."
)
SCANNED_MESSAGE = "This looks like a scanned image. Please upload a text-based PDF or a Word file."
ACTIVE_CONTENT_MESSAGE = (
    "This file contains macros, scripts or embedded content, which are not accepted. "
    "Save a plain copy and upload that."
)


@dataclass(frozen=True)
class FileProblem:
    code: str
    message: str


@dataclass(frozen=True)
class FileCheck:
    """`problem` is None for a file that is accepted. `notice` is something to tell the person
    about an accepted file (more pages than are read); `page_count` is None when unknown."""

    problem: FileProblem | None = None
    file_type: str | None = None
    page_count: int | None = None
    notice: str = ""
    flags: list = field(default_factory=list)


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


def pages_notice(page_count):
    read = get_setting("uploads.cv_pages_read")
    if page_count is not None and page_count > read:
        return f"This CV has {page_count} pages. Only the first {read} are read."
    return ""


def check_cv_file(name, data):
    """Everything about one file: refused with a reason, or accepted with its page count and
    any notice."""
    from . import docx_checks, pdf_checks

    if problem := check_name_and_size(name, len(data)):
        return FileCheck(problem=problem)
    claimed = file_type_of(name)
    kind = docx_checks.sniff(data) or pdf_checks.sniff(data)
    if kind != claimed:
        return FileCheck(
            problem=FileProblem(TYPE_MISMATCH, MISMATCH_MESSAGE.format(kind=claimed.upper()))
        )
    return (pdf_checks if kind == "pdf" else docx_checks).check(data)
