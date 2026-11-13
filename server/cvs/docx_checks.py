"""Word (DOCX) checks. A DOCX is a zip archive; it is measured from its headers before
anything is unpacked, and no part of it is ever run. Macros and embedded objects are refused."""

import re
import zipfile
from io import BytesIO

from platform_settings.service import get_setting

from . import file_checks as shared

ZIP_SIGNATURE = b"PK\x03\x04"
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")  # old Word files, and encrypted ones
ENCRYPTED_PART = "EncryptedPackage".encode("utf-16-le")
CONTENT_TYPES = "[Content_Types].xml"
MAIN_PART = "word/document.xml"
PROPERTIES_PART = "docProps/app.xml"
MAX_PROPERTIES_BYTES = 64 * 1024
PAGES = re.compile(rb"<Pages>\s*(\d{1,6})\s*</Pages>")
MACRO_PARTS = ("word/vbaproject.bin", "word/vbadata.xml")
EMBEDDED_PREFIXES = ("word/embeddings/", "word/activex/")
MACRO_CONTENT_TYPE = b"macroenabled"


def sniff(data):
    """ "docx" for a Word archive, "ole" for the old container (checked in `check`)."""
    if data.startswith(ZIP_SIGNATURE):
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return "docx"  # looks like Word but cannot be opened: reported as damaged
        return "docx" if MAIN_PART in names else None
    if data.startswith(OLE_SIGNATURE):
        return "docx" if ENCRYPTED_PART in data else None  # old .doc is not supported
    return None


def _refuse(code, message):
    return shared.FileCheck(problem=shared.FileProblem(code, message))


def _too_big_when_opened(archive):
    entries = archive.infolist()
    total = sum(entry.file_size for entry in entries)
    return len(entries) > get_setting("uploads.max_archive_entries") or total > (
        get_setting("uploads.max_unpacked_mb") * shared.BYTES_PER_MEGABYTE
    )


def _page_count(archive):
    try:
        info = archive.getinfo(PROPERTIES_PART)
    except KeyError:
        return None
    if info.file_size > MAX_PROPERTIES_BYTES:
        return None
    match = PAGES.search(archive.read(info))
    return int(match.group(1)) if match else None


def check(data):
    if data.startswith(OLE_SIGNATURE):
        return _refuse(shared.PASSWORD_PROTECTED, shared.PASSWORD_MESSAGE)
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            if MAIN_PART not in archive.namelist() or CONTENT_TYPES not in archive.namelist():
                return _refuse(shared.DAMAGED, shared.DAMAGED_MESSAGE)
            if _too_big_when_opened(archive):
                return _refuse(shared.DAMAGED, shared.DAMAGED_MESSAGE)
            lowered = [name.lower() for name in archive.namelist()]
            if any(name in MACRO_PARTS or name.startswith(EMBEDDED_PREFIXES) for name in lowered):
                return _refuse(shared.ACTIVE_CONTENT, shared.ACTIVE_CONTENT_MESSAGE)
            if MACRO_CONTENT_TYPE in archive.read(CONTENT_TYPES).lower():
                return _refuse(shared.ACTIVE_CONTENT, shared.ACTIVE_CONTENT_MESSAGE)
            page_count = _page_count(archive)
    except (zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError):
        return _refuse(shared.DAMAGED, shared.DAMAGED_MESSAGE)
    return shared.FileCheck(
        file_type="docx", page_count=page_count, notice=shared.pages_notice(page_count)
    )
