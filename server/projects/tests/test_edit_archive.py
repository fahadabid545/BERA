import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for
from plans import subscriptions as subs
from plans.models import Plan
from plans.summary import projects_in_use
from projects.models import Project
from projects.service import require_editable
from usage import service as usage

CV_ID = uuid.uuid4()

pytestmark = pytest.mark.django_db
LIST = "/api/company/projects/"


def url(project, suffix=""):
    return f"{LIST}{project.pk}/{suffix}"


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def make_project(company, person, title="Backend engineer", status="active"):
    return Project.objects.create(
        company=company,
        title=title,
        job_description="text " * 100,
        reading_model="model",
        created_by=person,
        status=status,
    )


@pytest.fixture
def company():
    company = make_company()
    now = timezone.now()
    plan = Plan.objects.create(
        name="Basic",
        status="active",
        price_usd=10,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=2,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=100000,
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


@pytest.fixture
def owner(company):
    return sign_in(company)


class TestReading:
    def test_the_detail_has_the_text_and_whether_delete_is_allowed(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        body = client.get(url(project)).json()
        assert body["title"] == "Backend engineer"
        assert body["status"] == "active"
        assert body["may_delete"] is True
        assert "reading_model" not in body and "reading_prompt_version" not in body

    def test_a_member_may_read_but_is_not_offered_delete(self, company, owner):
        project = make_project(company, owner[0])
        _, member = sign_in(company, role="member")
        assert member.get(url(project)).json()["may_delete"] is False

    def test_another_companys_project_is_not_found_in_every_way(self, company, owner):
        stranger = make_company()
        theirs = make_project(stranger, make_company_user(stranger))
        client = owner[1]
        assert client.get(url(theirs)).status_code == 404
        assert client.patch(url(theirs), {"title": "x"}, format="json").status_code == 404
        assert client.post(url(theirs, "archive/")).status_code == 404
        assert client.post(url(theirs, "restore/")).status_code == 404
        theirs.refresh_from_db()
        assert (theirs.title, theirs.status) == ("Backend engineer", "active")

    def test_a_made_up_identifier_is_not_found(self, owner):
        assert owner[1].get(f"{LIST}not-an-id/").status_code == 404

    def test_nobody_signed_in_is_refused(self, company, owner):
        project = make_project(company, owner[0])
        assert APIClient().get(url(project)).status_code == 401


class TestEditing:
    def test_title_and_description_change(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        before = project.updated_at
        response = client.patch(
            url(project), {"title": "New title", "job_description": "New text"}, format="json"
        )
        assert response.status_code == 200
        project.refresh_from_db()
        assert (project.title, project.job_description) == ("New title", "New text")
        assert project.updated_at > before

    def test_only_what_is_sent_changes(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        client.patch(url(project), {"title": "Only title"}, format="json")
        project.refresh_from_db()
        assert project.title == "Only title"
        assert project.job_description.startswith("text")

    def test_the_pinned_model_and_prompt_never_change(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        client.patch(url(project), {"title": "T"}, format="json")
        project.refresh_from_db()
        assert (project.reading_model, project.reading_prompt_version) == ("model", 1)
        assert client.patch(url(project), {"reading_model": "x"}, format="json").status_code == 400

    def test_an_empty_change_is_refused(self, company, owner):
        project = make_project(company, owner[0])
        assert owner[1].patch(url(project), {}, format="json").status_code == 400

    @pytest.mark.parametrize(
        "changes",
        [
            {"title": ""},
            {"title": "a" * 121},
            {"job_description": ""},
            {"job_description": "a" * 15001},
        ],
    )
    def test_the_same_rules_as_creating_apply(self, company, owner, changes):
        project = make_project(company, owner[0])
        assert owner[1].patch(url(project), changes, format="json").status_code == 400

    def test_a_member_may_edit(self, company, owner):
        project = make_project(company, owner[0])
        _, member = sign_in(company, role="member")
        assert member.patch(url(project), {"title": "By member"}, format="json").status_code == 200

    def test_an_archived_project_cannot_be_edited(self, company, owner):
        person, client = owner
        project = make_project(company, person, status="archived")
        response = client.patch(url(project), {"title": "Nope"}, format="json")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_archived"
        project.refresh_from_db()
        assert project.title == "Backend engineer"

    def test_an_archived_project_can_still_be_read(self, company, owner):
        project = make_project(company, owner[0], status="archived")
        assert owner[1].get(url(project)).status_code == 200


class TestArchiveAndRestore:
    def test_archive_then_restore(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        assert client.post(url(project, "archive/")).json()["status"] == "archived"
        project.refresh_from_db()
        assert project.status == "archived"
        assert client.post(url(project, "restore/")).json()["status"] == "active"
        project.refresh_from_db()
        assert project.status == "active"

    def test_a_member_may_archive_and_restore(self, company, owner):
        project = make_project(company, owner[0])
        _, member = sign_in(company, role="member")
        assert member.post(url(project, "archive/")).status_code == 200
        assert member.post(url(project, "restore/")).status_code == 200

    def test_archiving_twice_or_restoring_an_active_one_is_refused(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        assert (
            client.post(url(project, "restore/")).json()["error"]["code"] == "project_not_archived"
        )
        client.post(url(project, "archive/"))
        assert client.post(url(project, "archive/")).status_code == 409

    def test_the_helper_later_tickets_call_refuses_archived_only(self, company, owner):
        person, _ = owner
        require_editable(make_project(company, person))
        with pytest.raises(Exception) as caught:
            require_editable(make_project(company, person, "B", status="archived"))
        assert caught.value.code == "project_archived"

    def test_the_title_survives_archiving_and_restoring(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        client.post(url(project, "archive/"))
        client.post(url(project, "restore/"))
        project.refresh_from_db()
        assert project.title == "Backend engineer"


class TestProjectLimit:
    def test_archived_projects_do_not_count(self, company, owner):
        person, client = owner
        make_project(company, person, "A")
        make_project(company, person, "B", status="archived")
        make_project(company, person, "C", status="archived")
        assert projects_in_use(company.pk) == 1
        response = client.post(LIST, {"title": "D", "job_description": "x" * 400}, format="json")
        assert response.status_code == 201

    def test_archiving_frees_a_place(self, company, owner):
        person, client = owner
        first, _second = make_project(company, person, "A"), make_project(company, person, "B")
        body = {"title": "C", "job_description": "x" * 400}
        assert client.post(LIST, body, format="json").status_code == 409
        client.post(url(first, "archive/"))
        assert client.post(LIST, body, format="json").status_code == 201

    def test_restoring_counts_again_and_can_be_refused_at_the_limit(self, company, owner):
        person, client = owner
        archived = make_project(company, person, "Old", status="archived")
        make_project(company, person, "A")
        make_project(company, person, "B")
        response = client.post(url(archived, "restore/"))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_limit_reached"
        archived.refresh_from_db()
        assert archived.status == "archived"

    def test_past_usage_stays_in_history_when_archived(self, company, owner):
        person, client = owner
        project = make_project(company, person)
        usage.accept_cv(company.pk, CV_ID, project.pk)
        usage.mark_scored(company.pk, CV_ID)
        client.post(url(project, "archive/"))
        assert usage.current_usage(company.pk)["cvs_scored"] == 1
        assert usage.usage_history(company.pk)
