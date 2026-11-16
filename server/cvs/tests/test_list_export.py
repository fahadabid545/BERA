import io

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from activity.models import ActivityEntry
from cvs.models import Candidate, CvFile
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    tenant = Tenant(make_plan())
    add(tenant, "c-low.pdf", 40, ats=90, minutes=1)
    add(tenant, "a-high.pdf", 90, ats=50, minutes=2)
    add(tenant, "d-top.pdf", 95, ats=10, minutes=3)
    add(tenant, "waiting.pdf", None, status="waiting", minutes=4)
    return tenant


def export(tenant, file_format, query=""):
    url = f"/api/company/projects/{tenant.project.pk}/candidates/export/?as={file_format}{query}"
    return tenant.client.get(url)


def sheet_rows(response):
    sheet = load_workbook(io.BytesIO(response.content)).active
    return [list(row) for row in sheet.iter_rows(values_only=True)]


class TestSpreadsheet:
    def test_it_is_an_xlsx_file_to_save(self, tenant):
        response = export(tenant, "xlsx")
        assert response.status_code == 200
        assert response["Content-Type"].endswith("spreadsheetml.sheet")
        assert "attachment" in response["Content-Disposition"]
        assert response["Cache-Control"] == "private, no-store"

    def test_rows_follow_the_ranking_with_unscored_last(self, tenant):
        rows = sheet_rows(export(tenant, "xlsx"))
        assert rows[0][:3] == ["Rank", "Candidate", "File"]
        assert [row[2] for row in rows[1:]] == [
            "d-top.pdf",
            "a-high.pdf",
            "c-low.pdf",
            "waiting.pdf",
        ]
        assert rows[1][0] == 1 and rows[1][4] == 95.0 and rows[1][6] == 10

    def test_the_columns_say_stage_grade_recommendation_and_status(self, tenant):
        top = sheet_rows(export(tenant, "xlsx"))[1]
        assert (top[3], top[5], top[7], top[8]) == ("New", "A", "Strong match", "Done")
        waiting = sheet_rows(export(tenant, "xlsx"))[4]
        assert waiting[0] is None and waiting[4] is None and waiting[8] == "Waiting"

    def test_the_sort_and_filters_of_the_screen_apply(self, tenant):
        rows = sheet_rows(export(tenant, "xlsx", "&sort=ats&direction=desc"))
        assert [row[2] for row in rows[1:4]] == ["c-low.pdf", "a-high.pdf", "d-top.pdf"]

    def test_every_row_is_in_it_whatever_the_page_size(self, tenant):
        set_setting("candidates.page_size", 1)
        assert len(sheet_rows(export(tenant, "xlsx"))) == 5

    def test_the_candidate_is_initials_and_contact_details_are_absent(self, tenant):
        content = str(sheet_rows(export(tenant, "xlsx")))
        assert "Jane Example" not in content and "jane@example.com" not in content
        assert "J. E." in content

    def test_a_file_name_that_looks_like_a_formula_is_quoted(self, tenant):
        CvFile.objects.filter(original_name="a-high.pdf").update(original_name="=HYPERLINK(1).pdf")
        names = [row[2] for row in sheet_rows(export(tenant, "xlsx"))[1:]]
        assert "'=HYPERLINK(1).pdf" in names and "=HYPERLINK(1).pdf" not in names


class TestPdf:
    def test_it_is_a_pdf_with_the_list(self, tenant):
        response = export(tenant, "pdf")
        assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
        text = "".join(
            page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages
        )
        assert "d-top.pdf" in text and "Strong match" in text and "Rank" in text

    def test_a_long_list_runs_over_several_pages(self):
        tenant = Tenant(make_plan())
        for number in range(80):
            add(tenant, f"cv-{number:02d}.pdf", 50, minutes=number)
        reader = PdfReader(io.BytesIO(export(tenant, "pdf").content))
        assert len(reader.pages) > 1
        assert "Rank" in reader.pages[1].extract_text()  # the heading repeats

    def test_markup_in_a_file_name_is_shown_as_text(self, tenant):
        CvFile.objects.filter(original_name="a-high.pdf").update(original_name="<b>x</b>&.pdf")
        text = "".join(
            p.extract_text() for p in PdfReader(io.BytesIO(export(tenant, "pdf").content)).pages
        )
        assert "<b>x</b>&.pdf" in text


class TestRules:
    @pytest.mark.parametrize("value", ["", "csv", "docx"])
    def test_another_format_is_refused(self, tenant, value):
        response = export(tenant, value)
        assert response.status_code == 400 and "as" in response.json()["error"]["fields"]

    def test_the_download_is_logged(self, tenant):
        export(tenant, "pdf")
        (entry,) = ActivityEntry.objects.filter(company=tenant.company, kind="download")
        assert entry.details == {"scope": "list", "format": "pdf", "rows": 4}

    def test_a_refused_format_is_not_logged(self, tenant):
        export(tenant, "csv")
        assert not ActivityEntry.objects.filter(kind="download").exists()

    def test_another_company_gets_not_found(self, tenant):
        other = Tenant(make_plan())
        url = f"/api/company/projects/{tenant.project.pk}/candidates/export/?as=xlsx"
        assert other.client.get(url).status_code == 404

    def test_the_download_rate_limit_applies(self, tenant):
        set_setting("rate_limits.downloads_per_minute", 1)
        assert export(tenant, "xlsx").status_code == 200
        assert export(tenant, "xlsx").status_code == 429

    def test_the_route_does_not_clash_with_a_candidate(self, tenant):
        assert Candidate.objects.filter(project=tenant.project).exists()
        assert export(tenant, "xlsx").status_code == 200
