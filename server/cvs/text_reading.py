"""Reading the text out of a CV: `read_text(file_type, data)`, file in and text out.

Called by Background processing (and by the Create project form for a job description file)
after File checks accepted the file. Nothing is run: PDFs are read by pdfminer in a limited
process (`pdf_worker.py`), Word files by python-docx, both only as data.

A file with no usable text raises `CvTextUnreadable` ("We could not read this file."); the
caller does not count that CV (`usage.mark_failed`). Over-long text is trimmed and flagged."""

import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from core.errors import AppError
from platform_settings.service import get_setting

UNREADABLE_CODE = "cv_unreadable"
UNREADABLE_MESSAGE = "We could not read this file."
WORKER = Path(__file__).with_name("pdf_worker.py")

CID_PLACEHOLDER = re.compile(r"\(cid:\d+\)")
INVISIBLE = re.compile("[­​-‏‪-‮⁠-⁤﻿]")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f-\x9f]")
SPACES = re.compile(r"[^\S\n]+")  # any white space except line breaks
BLANK_LINES = re.compile(r"\n{3,}")
LINE_EDGE_SPACE = re.compile(r" ?\n ?")
TRIM_SEARCH_WINDOW = 200  # how far back to look for a place to cut that is not mid-word
FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
HEADING_STYLES = ("heading", "title")
LIST_STYLES = ("list",)


class CvTextUnreadable(AppError):
    def __init__(self):
        super().__init__(UNREADABLE_CODE, UNREADABLE_MESSAGE, status_code=422)


@dataclass(frozen=True)
class CvText:
    text: str
    trimmed: bool  # the text was longer than allowed and was cut


def clean_text(raw):
    """One tidy form for any language: composed characters, no invisible or control characters,
    ligatures and odd spaces made ordinary, and tidy blank lines."""
    text = unicodedata.normalize("NFKC", raw.replace("\x0c", "\n\n").replace("\r", "\n"))
    text = CID_PLACEHOLDER.sub("", text)  # a font with no text map: nothing real to keep
    text = CONTROL.sub("", INVISIBLE.sub("", text))
    text = SPACES.sub(" ", text)
    text = LINE_EDGE_SPACE.sub("\n", text)
    return BLANK_LINES.sub("\n\n", text).strip()


def trim_text(text, maximum):
    """Cuts to at most `maximum` characters at a word boundary where possible, never leaving a
    character cut off from the mark that belongs to it. Returns (text, was it cut)."""
    if len(text) <= maximum:
        return text, False
    cut = text[:maximum]
    boundary = max(cut.rfind(" "), cut.rfind("\n"))
    if boundary >= maximum - TRIM_SEARCH_WINDOW:
        cut = cut[:boundary]
    while cut and (unicodedata.combining(cut[-1]) or cut[-1] == "‍"):
        cut = cut[:-1]
    return cut.rstrip(), True


def _read_pdf(data):
    try:
        done = subprocess.run(
            [
                sys.executable,
                "-I",
                str(WORKER),
                str(get_setting("reading.worker_memory_mb")),
                str(get_setting("uploads.cv_pages_read")),
            ],
            input=data,
            capture_output=True,
            timeout=get_setting("reading.worker_timeout_seconds"),
            cwd="/",
            env={},
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CvTextUnreadable() from error
    if done.returncode != 0:
        raise CvTextUnreadable()
    return done.stdout.decode("utf-8", errors="replace")


def _paragraph_text(paragraph):
    style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
    text = paragraph.text.strip()
    if not text:
        return ""
    if (
        style.startswith(LIST_STYLES)
        or paragraph._p.pPr is not None
        and (paragraph._p.pPr.numPr is not None)
    ):
        return f"- {text}"
    return text if not style.startswith(HEADING_STYLES) else f"\n{text}\n"


def _table_text(table):
    lines = []
    for row in table.rows:
        seen, cells = set(), []
        for cell in row.cells:
            if id(cell._tc) in seen:  # a merged cell appears once per column it spans
                continue
            seen.add(id(cell._tc))
            value = " ".join(part for part in cell.text.split() if part)
            if value:
                cells.append(value)
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def _text_boxes(body):
    """Text inside text boxes (common for contact details in templates). Word stores each box
    twice, once in a fallback copy for old programs, which is skipped."""
    boxes = []
    for box in body.iter(qn("w:txbxContent")):
        if any(parent.tag == FALLBACK for parent in box.iterancestors()):
            continue
        lines = ["".join(t.text or "" for t in p.iter(qn("w:t"))) for p in box.iter(qn("w:p"))]
        boxes.append("\n".join(line.strip() for line in lines if line.strip()))
    return [box for box in boxes if box]


def _read_docx(data):
    document = Document(BytesIO(data))
    blocks = []
    for section in document.sections[:1]:  # contact details are often in the page header
        header = "\n".join(p.text.strip() for p in section.header.paragraphs if p.text.strip())
        if header:
            blocks.append(header)
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            blocks.append(_paragraph_text(Paragraph(child, document)))
        elif child.tag == qn("w:tbl"):
            blocks.append(_table_text(Table(child, document)))
    blocks.extend(_text_boxes(document.element.body))
    return "\n\n".join(block for block in blocks if block)


def read_text(file_type, data, *, max_characters=None):
    """The text of a PDF (first `uploads.cv_pages_read` pages) or Word file, in reading order
    (two-column pages column by column; headings, lists and tables kept as lines), cleaned,
    and trimmed to `max_characters` (default `reading.max_characters`)."""
    try:
        raw = _read_pdf(data) if file_type == "pdf" else _read_docx(data)
    except CvTextUnreadable:
        raise
    except Exception as error:  # a damaged file can break the reader in many ways
        raise CvTextUnreadable() from error
    text = clean_text(raw)
    if sum(character.isalnum() for character in text) < get_setting("reading.min_characters"):
        raise CvTextUnreadable()
    text, trimmed = trim_text(text, max_characters or get_setting("reading.max_characters"))
    return CvText(text=text, trimmed=trimmed)
