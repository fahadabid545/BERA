import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

import privatefiles
from core.tests.factories import make_company, make_company_user, start_session_for
from cvs.downloads import download_link_for_cv
from cvs.models import CvFile
from cvs.tests.files import make_pdf
from plans import subscriptions as subs
from plans.models import Plan
from projects.models import Project

pytestmark = pytest.mark.django_db


class SignedIn:
    """What the permission check reads from a request's user."""

    kind = "company"

    def __init__(self, person, role):
        self.company_id, self.user_id, self.role = person.company_id, person.pk, role


def person_of(company, role="owner"):
    person = make_company_user(company, role=role)
    return person, SignedIn(person, role)


@pytest.fixture
def company():
    from django.utils import timezone

    company = make_company()
    now = timezone.now()
    plan = Plan.objects.create(
        name="Basic",
        status="active",
        price_usd=10,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=10000,
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


@pytest.fixture
def owner(company):
    return person_of(company)


@pytest.fixture
def stored_cv(company, owner):
    owner = owner[0]
    project = Project.objects.create(
        company=company,
        title="T",
        job_description="t",
        reading_model="m",
        created_by=owner,
    )
    issued = start_session_for(
        user_id=owner.pk, role="owner", company_id=company.pk, kind="company"
    )
    client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
    client.post(
        f"/api/company/projects/{project.pk}/cvs/",
        {"files": [SimpleUploadedFile("Jane CV.pdf", make_pdf())]},
        format="multipart",
    )
    return CvFile.objects.get(project=project)


class TestPermissionCheckBeforeALink:
    def test_the_owner_gets_a_short_lived_link_that_gives_the_file(self, owner, stored_cv):
        user = owner[1]
        link = download_link_for_cv(user, stored_cv.pk)
        assert link["url"].startswith("/api/files/")
        data, name = privatefiles.read_for_link(link["url"].split("/")[3])
        assert data == make_pdf()
        assert name == "Jane CV.pdf"

    def test_a_member_may_download_too(self, company, stored_cv):
        _, member = person_of(company, "member")
        assert download_link_for_cv(member, stored_cv.pk)["url"]

    def test_another_companys_file_is_not_found(self, stored_cv):
        _, outsider = person_of(make_company())
        with pytest.raises(Http404):
            download_link_for_cv(outsider, stored_cv.pk)

    def test_a_file_that_does_not_exist_looks_the_same(self, owner):
        import uuid

        user = owner[1]
        with pytest.raises(Http404):
            download_link_for_cv(user, uuid.uuid4())

    def test_a_made_up_identifier_looks_the_same(self, owner):
        user = owner[1]
        with pytest.raises(Http404):
            download_link_for_cv(user, "not-an-id")

    def test_a_role_that_may_not_download_is_refused(self, company, stored_cv, monkeypatch):
        from companies import role_matrix

        monkeypatch.setitem(role_matrix.ROLES_ALLOWED, "cv.download", role_matrix.OWNER_ONLY)
        _, member = person_of(company, "member")
        with pytest.raises(PermissionDenied):
            download_link_for_cv(member, stored_cv.pk)

    def test_someone_who_is_not_a_company_user_is_refused(self, stored_cv):
        class Admin:
            kind = "admin"
            company_id = None
            role = "super"

        with pytest.raises(PermissionDenied):
            download_link_for_cv(Admin(), stored_cv.pk)

    def test_an_archived_project_can_still_be_downloaded_from(self, owner, stored_cv):
        Project.objects.filter(pk=stored_cv.project_id).update(status="archived")
        user = owner[1]
        assert download_link_for_cv(user, stored_cv.pk)["url"]


class TestNoPublicAddress:
    def test_no_route_serves_the_storage_folder(self):
        from django.urls import Resolver404, resolve

        for path in ("/local_storage/cvs/1/a", "/media/cvs/1/a", "/static/cvs/1/a", "/cvs/1/a"):
            with pytest.raises(Resolver404):
                resolve(path)

    def test_the_stored_key_gives_nothing_to_a_visitor(self, stored_cv):
        response = APIClient().get(f"/{stored_cv.storage_key}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_a_forged_link_gives_nothing(self):
        with pytest.raises(privatefiles.InvalidLink):
            privatefiles.read_for_link("cvs/1/a")
