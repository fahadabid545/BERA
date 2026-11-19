import io
import zipfile

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient

import privatefiles
from activity.models import ActivityEntry
from core.tests.factories import make_company_user, start_session_for
from cvs import download_packages
from cvs.models import DownloadPackage
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add
from emailing.models import OutgoingEmail
from projects.models import Project

pytestmark = pytest.mark.django_db

EXPORT = "/api/company/downloads/export/"


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def stored(tenant, name, score=70, project=None, **fields):
    if project is not None:
        tenant.project, original = project, tenant.project
    try:
        row = add(tenant, name, score, **fields)
    finally:
        if project is not None:
            tenant.project = original
    privatefiles.save_file(row.storage_key, f"bytes of {name}".encode())
    return row


def second_project(tenant, title="Second"):
    return Project.objects.create(
        company=tenant.company,
        title=title,
        job_description="t",
        reading_model="m",
        created_by=tenant.owner,
    )


def get_zip(tenant, response):
    file = tenant.client.get(f"/api/company/downloads/{response.json()['id']}/file/")
    assert file.status_code == 200
    return zipfile.ZipFile(io.BytesIO(file.content))


class TestTheExport:
    def test_every_project_gets_a_folder_with_its_cvs_and_its_ranked_list(self, tenant):
        stored(tenant, "a.pdf", minutes=1)
        stored(tenant, "b.pdf", minutes=2, project=second_project(tenant, "Designer"))
        response = tenant.client.post(EXPORT, {}, format="json")
        assert response.status_code == 201
        assert response.json()["project_id"] is None
        assert (response.json()["status"], response.json()["files"]) == ("ready", 2)
        names = sorted(get_zip(tenant, response).namelist())
        assert names == [
            "Designer/b.pdf",
            "Designer/ranked-list.xlsx",
            "T/a.pdf",
            "T/ranked-list.xlsx",
        ]

    def test_the_files_are_the_real_ones(self, tenant):
        stored(tenant, "a.pdf")
        archive = get_zip(tenant, tenant.client.post(EXPORT, {}, format="json"))
        assert archive.read("T/a.pdf") == b"bytes of a.pdf"

    def test_the_ranked_list_holds_no_contact_details(self, tenant):
        stored(tenant, "a.pdf", who="Jane Example")
        archive = get_zip(tenant, tenant.client.post(EXPORT, {}, format="json"))
        sheet = load_workbook(io.BytesIO(archive.read("T/ranked-list.xlsx"))).active
        text = " ".join(str(cell.value) for row in sheet.iter_rows() for cell in row)
        assert "a.pdf" in text and "jane@example.com" not in text and "Jane Example" not in text

    def test_two_projects_with_one_title_get_separate_folders(self, tenant):
        stored(tenant, "a.pdf", minutes=1)
        stored(tenant, "b.pdf", minutes=2, project=second_project(tenant, "T"))
        names = get_zip(tenant, tenant.client.post(EXPORT, {}, format="json")).namelist()
        assert sum(name.endswith("ranked-list.xlsx") for name in names) == 2
        assert {name.split("/")[0] for name in names} == {"T", "T (2)"}

    def test_cancelled_cvs_are_left_out(self, tenant):
        stored(tenant, "a.pdf", minutes=1)
        stored(tenant, "gone.pdf", None, status="cancelled", minutes=2)
        names = get_zip(tenant, tenant.client.post(EXPORT, {}, format="json")).namelist()
        assert "T/gone.pdf" not in names

    def test_a_company_with_no_cvs_has_nothing_to_export(self, tenant):
        response = tenant.client.post(EXPORT, {}, format="json")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "nothing_to_download"

    def test_another_companys_cvs_are_never_in_it(self, tenant):
        stored(tenant, "mine.pdf")
        theirs = Tenant(make_plan())
        stored(theirs, "theirs.pdf")
        names = get_zip(tenant, tenant.client.post(EXPORT, {}, format="json")).namelist()
        assert not any("theirs" in name for name in names)

    def test_a_large_export_is_made_in_the_background_and_the_owner_is_emailed(
        self, tenant, monkeypatch
    ):
        set_setting("downloads.background_over_files", 1)
        stored(tenant, "a.pdf", minutes=1)
        stored(tenant, "b.pdf", minutes=2)
        queued = []
        monkeypatch.setattr(download_packages, "async_task", lambda *args: queued.append(args))
        response = tenant.client.post(EXPORT, {}, format="json")
        assert response.json()["status"] == "preparing"
        download_packages.build_package(response.json()["id"])
        package = DownloadPackage.objects.get()
        assert package.status == "ready" and package.project_id is None
        mails = list(OutgoingEmail.objects.filter(template="download_ready"))
        assert len(mails) == 1 and mails[0].to_address == tenant.owner.email

    def test_the_download_is_logged_without_a_project(self, tenant):
        stored(tenant, "a.pdf")
        get_zip(tenant, tenant.client.post(EXPORT, {}, format="json"))
        entry = ActivityEntry.objects.get(kind="download")
        assert (entry.target_kind, entry.target_id) == ("", "")
        assert entry.details == {"scope": "package", "files": 1}


class TestOwnerOnly:
    def test_a_member_cannot_ask_for_it(self, tenant):
        stored(tenant, "a.pdf")
        member = make_company_user(tenant.company, role="member")
        issued = start_session_for(
            user_id=member.pk, role="member", company_id=tenant.company.pk, kind="company"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.post(EXPORT, {}, format="json").status_code == 403
        assert not DownloadPackage.objects.exists()

    def test_signed_out_is_refused(self):
        assert APIClient().post(EXPORT, {}, format="json").status_code == 401

    def test_nobody_else_can_fetch_the_zip(self, tenant):
        stored(tenant, "a.pdf")
        response = tenant.client.post(EXPORT, {}, format="json")
        other = Tenant(make_plan())
        file = other.client.get(f"/api/company/downloads/{response.json()['id']}/file/")
        assert file.status_code == 404
