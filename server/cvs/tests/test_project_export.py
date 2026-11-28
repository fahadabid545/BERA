import io

import pytest
from openpyxl import load_workbook

from activity.models import ActivityEntry
from companies.models import CompanyUser
from cvs.models import Candidate, CandidateNote
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add
from projects.models import Requirement

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    tenant = Tenant(make_plan())
    add(tenant, "a-high.pdf", 90, ats=50, minutes=2)
    Requirement.objects.create(
        company_id=tenant.company.pk, project=tenant.project, position=0, kind="must",
        text="Python experience", weight=5,
    )  # fmt: skip
    return tenant


def download(tenant):
    return tenant.client.get(f"/api/company/projects/{tenant.project.pk}/export/")


def sheets(response):
    book = load_workbook(io.BytesIO(response.content))
    return {sheet.title: [list(row) for row in sheet.iter_rows(values_only=True)] for sheet in book}


class TestProjectExport:
    def test_it_holds_requirements_the_ranked_list_and_notes(self, tenant):
        response = download(tenant)
        assert response.status_code == 200
        assert list(sheets(response)) == ["Requirements", "Ranked list", "Notes"]

    def test_the_requirements_sheet_lists_each_requirement(self, tenant):
        rows = sheets(download(tenant))["Requirements"]
        assert rows[1] == [1, "Must", "Python experience", 5]

    def test_the_ranked_list_has_the_scored_candidate(self, tenant):
        rows = sheets(download(tenant))["Ranked list"]
        assert rows[1][2] == "a-high.pdf" and rows[1][4] == 90.0

    def test_notes_are_listed_with_their_author(self, tenant):
        candidate = Candidate.objects.get(cv_file__original_name="a-high.pdf")
        author = CompanyUser.objects.filter(company_id=tenant.company.pk).first()
        CandidateNote.objects.create(
            company_id=tenant.company.pk, candidate=candidate, author=author, text="Call back"
        )
        rows = sheets(download(tenant))["Notes"]
        assert rows[1][1:3] == ["a-high.pdf", author.name] and rows[1][4] == "Call back"

    def test_a_note_starting_with_a_formula_sign_is_stored_as_text(self, tenant):
        candidate = Candidate.objects.get(cv_file__original_name="a-high.pdf")
        author = CompanyUser.objects.filter(company_id=tenant.company.pk).first()
        CandidateNote.objects.create(
            company_id=tenant.company.pk, candidate=candidate, author=author, text="=1+1"
        )
        assert not sheets(download(tenant))["Notes"][1][4].startswith("=")

    def test_an_empty_project_still_downloads(self, tenant):
        Candidate.objects.all().delete()
        Requirement.objects.all().delete()
        rows = sheets(download(tenant))
        assert len(rows["Requirements"]) == 1 and len(rows["Notes"]) == 1

    def test_the_download_is_logged_without_contact_details(self, tenant):
        download(tenant)
        entry = ActivityEntry.objects.get(kind="download")
        assert entry.details == {"scope": "project", "format": "xlsx"}

    def test_it_is_private_and_not_cached(self, tenant):
        response = download(tenant)
        assert "no-store" in response["Cache-Control"]

    def test_another_company_gets_not_found(self, tenant):
        from core.tests.factories import make_company
        from projects.tests.helpers import sign_in

        _, stranger = sign_in(make_company())
        assert stranger.get(f"/api/company/projects/{tenant.project.pk}/export/").status_code == 404


class TestStageMovesAreInTheHistory:
    def test_a_bulk_move_is_listed_once_and_a_no_op_is_not(self, tenant):
        candidate = Candidate.objects.get(cv_file__original_name="a-high.pdf")
        link = f"/api/company/projects/{tenant.project.pk}/candidates/stage/"
        tenant.client.post(
            link, {"candidate_ids": [str(candidate.pk)], "stage": "shortlisted"}, format="json"
        )
        tenant.client.post(
            link, {"candidate_ids": [str(candidate.pk)], "stage": "shortlisted"}, format="json"
        )
        history = tenant.client.get(f"/api/company/projects/{tenant.project.pk}/history/").json()
        assert [e["details"]["change"] for e in history["entries"]] == ["stages"]
