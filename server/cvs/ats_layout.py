"""What a CV file looks like to an ATS beyond its text: how many pages, and which pages are
mostly a picture. Read as data with pypdf under the same limits as the upload checks; a file
that cannot be read this way simply reports nothing special (the upload checks already refused
damaged files)."""

import logging
from io import BytesIO

from pypdf import PdfReader

from platform_settings.service import get_setting

from .ats import Layout
from .pdf_checks import unpack_limit

logger = logging.getLogger(__name__)


def _is_picture_page(page):
    try:
        has_picture = bool(page.images)
    except Exception:  # a picture pypdf cannot decode still is a picture
        has_picture = True
    if not has_picture:
        return False
    return len((page.extract_text() or "").strip()) < get_setting("ats.image_page_min_characters")


def layout_of(file_type, data, page_count=None):
    """The `Layout` of a stored file. Only PDFs have pages of pictures to find."""
    if file_type != "pdf":
        return Layout(page_count=page_count)
    try:
        with unpack_limit():
            reader = PdfReader(BytesIO(data), strict=False)
            pages = list(reader.pages[: get_setting("uploads.cv_pages_read")])
            image_pages = sum(_is_picture_page(page) for page in pages)
            return Layout(page_count=len(reader.pages), image_pages=image_pages)
    except Exception:
        logger.warning("The layout of a PDF could not be read.")
        return Layout(page_count=page_count)
