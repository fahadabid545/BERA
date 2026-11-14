"""Notes on a candidate. Any member of the company can add one; only its author can change or
remove it. A note's text is never written to logs."""

from django.core.exceptions import ValidationError
from django.http import Http404

from core.errors import AppError, form_error
from platform_settings.service import get_setting

from .models import CandidateNote


def _checked_text(raw):
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        raise form_error({"text": "Write the note."})
    if len(text) > get_setting("notes.max_length"):
        raise form_error({"text": "The note is too long."})
    return text


def note_entry(note, user_id):
    return {
        "id": str(note.pk),
        "text": note.text,
        "author": note.author.name,
        "mine": note.author_id == user_id,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


def notes_of(candidate, user_id):
    notes = CandidateNote.objects.filter(candidate=candidate).select_related("author")
    return [note_entry(note, user_id) for note in notes.order_by("-created_at", "-pk")]


def add_note(candidate, user_id, raw_text):
    note = CandidateNote.objects.create(
        company_id=candidate.company_id,
        candidate=candidate,
        author_id=user_id,
        text=_checked_text(raw_text),
    )
    return note_entry(note, user_id)


def _own_note(candidate, user_id, note_id):
    try:
        note = CandidateNote.objects.select_related("author").get(
            pk=note_id, candidate=candidate, company_id=candidate.company_id
        )
    except (CandidateNote.DoesNotExist, ValueError, ValidationError):
        raise Http404 from None
    if note.author_id != user_id:
        raise AppError(
            "not_note_author", "Only the person who wrote a note can change it.", status_code=403
        )
    return note


def change_note(candidate, user_id, note_id, raw_text):
    note = _own_note(candidate, user_id, note_id)
    note.text = _checked_text(raw_text)
    note.save(update_fields=["text", "updated_at"])
    return note_entry(note, user_id)


def remove_note(candidate, user_id, note_id):
    _own_note(candidate, user_id, note_id).delete()
