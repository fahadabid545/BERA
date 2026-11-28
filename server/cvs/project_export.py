"""The whole project in one spreadsheet: its requirements, the ranked list with scores, and the
team's notes on candidates. Candidates are initials only and contact details are never in it."""

import io

from django.http import HttpResponse
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from openpyxl.styles import Font

from activity.service import record
from companies.models import CompanyUser
from core.personal_data import mask_name
from core.spreadsheets import safe_cell

from .list_export import add_ranked_sheet
from .models import CandidateNote
from .ranking import all_ranked_rows

CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILE_NAME = "project.xlsx"
REQUIREMENT_HEADINGS = ("Position", "Kind", "Requirement", "Weight")
NOTE_HEADINGS = ("Candidate", "File", "Author", "Written", "Note")


def _sheet(workbook, title, headings, rows):
    sheet = workbook.create_sheet(title)
    sheet.append(list(headings))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([safe_cell(value) if isinstance(value, str) else value for value in row])
    sheet.freeze_panes = "A2"


def _requirement_rows(project):
    return [
        (item.position + 1, item.kind.capitalize(), item.text, item.weight)
        for item in project.requirements.order_by("position")
    ]


def _masked_name(cv_file):
    contact = getattr(cv_file, "contact", None)
    return mask_name(contact.name) if contact and contact.name else ""


def _note_rows(project):
    notes = CandidateNote.objects.filter(candidate__project=project).select_related(
        "candidate__cv_file__contact", "author"
    )
    return [
        (
            _masked_name(note.candidate.cv_file),
            note.candidate.cv_file.original_name,
            note.author.name,
            note.created_at.strftime("%Y-%m-%d %H:%M"),
            note.text,
        )
        for note in notes.order_by("candidate__number", "created_at")
    ]


def project_workbook(project):
    workbook = Workbook()
    workbook.remove(workbook.active)
    _sheet(workbook, "Requirements", REQUIREMENT_HEADINGS, _requirement_rows(project))
    add_ranked_sheet(workbook, all_ranked_rows(project, {}))
    _sheet(workbook, "Notes", NOTE_HEADINGS, _note_rows(project))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def project_export_response(project, user):
    person = CompanyUser.objects.get(pk=user.user_id, company_id=project.company_id)
    record(
        "download",
        company_id=project.company_id,
        actor=person,
        target_kind="project",
        target_id=project.pk,
        details={"scope": "project", "format": "xlsx"},
    )
    response = HttpResponse(project_workbook(project), content_type=CONTENT_TYPE)
    response["Content-Disposition"] = content_disposition_header(True, FILE_NAME)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
