"""The ranked list as a spreadsheet (.xlsx) or a PDF, in the order and with the filters the
person has on screen. It holds what the list shows: the candidate as initials, the file name,
stage, scores and recommendation; contact details are never in it."""

import io
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from activity.service import record
from companies.models import CompanyUser
from core.errors import form_error
from core.spreadsheets import safe_cell

from .ranking import all_ranked_rows

FORMATS = {
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ranked-list.xlsx",
    ),
    "pdf": ("application/pdf", "ranked-list.pdf"),
}
HEADINGS = (
    "Rank",
    "Candidate",
    "File",
    "Stage",
    "AI score",
    "Grade",
    "ATS score",
    "Recommendation",
    "Status",
)
LABELS = {
    "strong_match": "Strong match",
    "possible": "Possible",
    "not_recommended": "Not recommended",
}
WIDTHS = (8, 14, 40, 14, 10, 8, 10, 20, 14)
PDF_MARGIN = 28
PDF_FONT_SIZE = 8


def _words(value):
    return value.replace("_", " ").capitalize() if value else ""


def _cells(row):
    """One row of the list as the values a person reads; numbers stay numbers."""
    return [
        row["rank"],
        row["name"],
        row["file_name"],
        _words(row["stage"]),
        float(row["score"]) if row["score"] is not None else None,
        row["grade"] or "",
        row["ats_score"],
        LABELS.get(row["label"], ""),
        _words(row["status"]),
    ]


def _spreadsheet(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ranked list"
    sheet.append(list(HEADINGS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([safe_cell(v) if isinstance(v, str) else v for v in _cells(row)])
    sheet.freeze_panes = "A2"
    for column, width in zip("ABCDEFGHI", WIDTHS, strict=True):
        sheet.column_dimensions[column].width = width
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _pdf(rows, title):
    styles = getSampleStyleSheet()
    cell_style = styles["BodyText"].clone("cell", fontSize=PDF_FONT_SIZE, leading=PDF_FONT_SIZE + 2)
    body = [
        [Paragraph(escape("" if v is None else str(v)), cell_style) for v in _cells(row)]
        for row in rows
    ]
    table = Table([list(HEADINGS), *body], repeatRows=1, colWidths=[w * 5.2 for w in WIDTHS])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), PDF_FONT_SIZE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=PDF_MARGIN,
        rightMargin=PDF_MARGIN,
        topMargin=PDF_MARGIN,
        bottomMargin=PDF_MARGIN,
        title=title,
    )
    document.build([Paragraph(escape(title), styles["Title"]), table])
    return buffer.getvalue()


def ranked_list_xlsx(project):
    """The project's whole ranked list as spreadsheet bytes, for the company export."""
    return _spreadsheet(all_ranked_rows(project, {}))


def export_response(project, user, params, file_format):
    """The list as a file to save, and an entry in the activity log."""
    if file_format not in FORMATS:
        raise form_error({"as": "Choose spreadsheet or PDF."})
    rows = all_ranked_rows(project, params)
    data = _spreadsheet(rows) if file_format == "xlsx" else _pdf(rows, project.title)
    person = CompanyUser.objects.get(pk=user.user_id, company_id=project.company_id)
    record(
        "download",
        company_id=project.company_id,
        actor=person,
        target_kind="project",
        target_id=project.pk,
        details={"scope": "list", "format": file_format, "rows": len(rows)},
    )
    content_type, file_name = FORMATS[file_format]
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = content_disposition_header(True, file_name)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
