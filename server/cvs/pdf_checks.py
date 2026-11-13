"""PDF checks. The file is read as data with pypdf: nothing in it is executed, and its scripts,
launch actions and attachments are only looked for, never opened."""

import logging
from io import BytesIO

from pypdf import PdfReader, apply_configuration

from platform_settings.service import get_setting

from . import file_checks as shared

logger = logging.getLogger(__name__)

SIGNATURE = b"%PDF-"
SIGNATURE_WINDOW = 1024  # the format allows a little leading data before the signature
ACTIVE_ACTIONS = {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/RichMediaExecute"}


def sniff(data):
    return "pdf" if SIGNATURE in data[:SIGNATURE_WINDOW] else None


def _action_is_active(action):
    action = action.get_object() if hasattr(action, "get_object") else action
    return isinstance(action, dict) and action.get("/S") in ACTIVE_ACTIONS


def _has_active_content(reader, pages_to_look_at):
    """Scripts, launch actions or attachments in the document or in the pages that are read.
    Names and structure are checked, so hiding a keyword in the file's text does not matter."""
    root = reader.trailer["/Root"]
    if "/AA" in root:
        return True
    if "/XFA" in root.get("/AcroForm", {}):
        return True
    if "/OpenAction" in root and _action_is_active(root["/OpenAction"]):
        return True
    names = root.get("/Names", {})
    if "/JavaScript" in names or "/EmbeddedFiles" in names:
        return True
    for page in pages_to_look_at:
        if "/AA" in page:
            return True
        for annotation in page.get("/Annots", []) or []:
            annotation = annotation.get_object()
            if "/A" in annotation and _action_is_active(annotation["/A"]):
                return True
            if annotation.get("/Subtype") in ("/FileAttachment", "/RichMedia", "/Movie"):
                return True
    return False


def _has_text(pages):
    return any((page.extract_text() or "").strip() for page in pages)


def _unpack_limit():
    """pypdf's own caps on how much a compressed part may unpack to, held to the platform's
    for the time of one check (the context manager restores them afterwards)."""
    limit = get_setting("uploads.max_unpacked_mb") * shared.BYTES_PER_MEGABYTE
    return apply_configuration(
        zlib_maximum_output_length=limit,
        lzw_maximum_output_length=limit,
        run_length_maximum_output_length=limit,
        jbig2_maximum_output_length=limit,
        array_based_stream_maximum_output_length=limit,
        maximum_declared_stream_length=limit,
    )


def check(data):
    try:
        with _unpack_limit():
            return _read(data)
    except Exception:  # pypdf raises many kinds of error for broken files; all mean "damaged"
        logger.warning("A PDF could not be read.")
        return _damaged()


def _damaged():
    return shared.FileCheck(problem=shared.FileProblem(shared.DAMAGED, shared.DAMAGED_MESSAGE))


def _read(data):
    reader = PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted:
        return shared.FileCheck(
            problem=shared.FileProblem(shared.PASSWORD_PROTECTED, shared.PASSWORD_MESSAGE)
        )
    page_count = len(reader.pages)
    if page_count == 0:
        return _damaged()
    read = get_setting("uploads.cv_pages_read")
    pages = [reader.pages[index] for index in range(min(page_count, read))]
    if _has_active_content(reader, pages):
        return shared.FileCheck(
            problem=shared.FileProblem(shared.ACTIVE_CONTENT, shared.ACTIVE_CONTENT_MESSAGE)
        )
    if not _has_text(pages):
        return shared.FileCheck(
            problem=shared.FileProblem(shared.SCANNED_IMAGE, shared.SCANNED_MESSAGE)
        )
    return shared.FileCheck(
        file_type="pdf", page_count=page_count, notice=shared.pages_notice(page_count)
    )
