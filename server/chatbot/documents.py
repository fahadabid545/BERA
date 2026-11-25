"""The chatbot's knowledge documents: public product information uploaded by a super admin.

A file goes through the same checks as a CV (its real type, damaged, password protected, macros,
scanned image) and the same text reading, then its extracted text is kept. Text and Markdown files
are read as plain UTF-8 text. A document that is too large, too long or too many is refused.
Nothing here reads any company data, and nothing in it is a company's.
"""

from django.db import transaction
from django.db.models import Sum

from audit.service import record
from core.errors import AppError
from cvs.file_checks import BYTES_PER_MEGABYTE, check_content
from cvs.text_reading import CvTextUnreadable, clean_text, read_text, trim_text
from platform_settings.service import get_setting

from .models import KnowledgeDocument

PLAIN_TEXT_TYPES = ("txt", "md")
NOT_FOUND = "There is no such document."


def _file_type(name):
    ending = str(name).rpartition(".")[2].lower() if "." in str(name) else ""
    return ending if ending in get_setting("chatbot.document_types") else None


def _refuse(code, message):
    return AppError(code, message, status_code=400, fields={"file": message})


def _plain_text(data):
    if b"\x00" in data:
        raise _refuse("document_unreadable", "This file is not a text file.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise _refuse("document_unreadable", "This text file must be saved as UTF-8.") from error


def _read(file_type, data, limit):
    """The cleaned text of the file, refused if it holds too little or more than `limit`."""
    if file_type in PLAIN_TEXT_TYPES:
        text = clean_text(_plain_text(data))
        enough = sum(character.isalnum() for character in text) >= get_setting(
            "reading.min_characters"
        )
        if not enough:
            raise _refuse("document_unreadable", "This file has too little text.")
        text, trimmed = trim_text(text, limit)
    else:
        problem = check_content(file_type, data)
        if problem.problem:
            raise _refuse(problem.problem.code, problem.problem.message)
        if problem.notice:
            raise _refuse("document_too_long", problem.notice)
        try:
            read = read_text(file_type, data, max_characters=limit)
        except CvTextUnreadable as error:
            raise _refuse("document_unreadable", error.message) from error
        text, trimmed = read.text, read.trimmed
    if trimmed:
        raise _refuse(
            "document_too_long", f"This document is longer than {limit} characters. Split it."
        )
    return text


def _checked(name, data, *, ignoring=None):
    """(file type, text) of an upload, or a refusal. `ignoring` is the document being replaced,
    which does not count toward the number or the total size."""
    name = (name or "").strip()
    file_type = _file_type(name)
    if file_type is None:
        allowed = ", ".join(kind.upper() for kind in get_setting("chatbot.document_types"))
        raise _refuse("document_wrong_type", f"Only {allowed} files can be added.")
    if not data:
        raise _refuse("document_empty", "This file is empty.")
    largest = get_setting("chatbot.max_document_size_mb")
    if len(data) > largest * BYTES_PER_MEGABYTE:
        raise _refuse("document_too_large", f"This file is larger than {largest} MB.")
    others = KnowledgeDocument.objects.all()
    if ignoring:
        others = others.exclude(pk=ignoring.pk)
    if ignoring is None and others.count() >= get_setting("chatbot.max_documents"):
        raise _refuse("document_limit", "There are too many documents. Delete one first.")
    total = (others.aggregate(total=Sum("size_bytes"))["total"] or 0) + len(data)
    if total > get_setting("chatbot.max_total_size_mb") * BYTES_PER_MEGABYTE:
        raise _refuse("document_total_limit", "The documents would be too large together.")
    return file_type, _read(file_type, data, get_setting("chatbot.max_document_characters"))


def describe(document):
    """What the admin page shows (never the text itself)."""
    return {
        "id": document.pk,
        "name": document.name,
        "file_type": document.file_type,
        "size_bytes": document.size_bytes,
        "characters": len(document.text),
        "enabled": document.enabled,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


def list_documents():
    return [describe(document) for document in KnowledgeDocument.objects.all()]


def _get(document_id):
    document = KnowledgeDocument.objects.select_for_update().filter(pk=document_id).first()
    if document is None:
        raise AppError("document_not_found", NOT_FOUND, status_code=404)
    return document


def add(admin, *, name, data):
    with transaction.atomic():
        file_type, text = _checked(name, data)
        document = KnowledgeDocument.objects.create(
            name=name.strip()[:200], file_type=file_type, size_bytes=len(data), text=text
        )
        record(
            "admin.chatbot_document_added",
            actor=admin,
            details={"document": document.pk, "file_type": file_type},
        )
    return document


def replace(admin, document_id, *, name, data):
    """The document keeps its place and its on/off state; its name, text and size change."""
    with transaction.atomic():
        document = _get(document_id)
        file_type, text = _checked(name, data, ignoring=document)
        document.name, document.file_type = name.strip()[:200], file_type
        document.size_bytes, document.text = len(data), text
        document.save()
        record(
            "admin.chatbot_document_replaced",
            actor=admin,
            details={"document": document.pk, "file_type": file_type},
        )
    return document


def switch(admin, document_id, *, enabled):
    with transaction.atomic():
        document = _get(document_id)
        if document.enabled == enabled:
            raise AppError("nothing_changed", "Nothing was changed.", status_code=400)
        document.enabled = enabled
        document.save(update_fields=["enabled", "updated_at"])
        record(
            "admin.chatbot_document_switched",
            actor=admin,
            details={"document": document.pk, "enabled": enabled},
        )
    return document


def delete(admin, document_id):
    with transaction.atomic():
        document = _get(document_id)
        document.delete()
        record("admin.chatbot_document_deleted", actor=admin, details={"document": document_id})


def knowledge_texts():
    """The (name, text) of every document that is switched on: what the chatbot may use. This is
    all the later chat feature reads; it never needs a company's data."""
    return list(KnowledgeDocument.objects.filter(enabled=True).values_list("name", "text"))
