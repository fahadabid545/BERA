"""Deleting a project removes everything that belongs to it.

When a ticket stores new project data it registers it in `projects/deletion.py` and adds its
name to EXPECTED_REGISTRATIONS here; the guard test below fails until both are done."""

import uuid

import pytest
from django.apps import apps
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import ActivityEntry
from core.tests.factories import make_company, make_company_user, start_session_for
from plans import subscriptions as subs
from plans.models import Plan
from projects import deletion
from projects.models import Project
from usage import service as usage

CV_ID = uuid.uuid4()

pytestmark = pytest.mark.django_db

# Names of everything registered with register_project_data, one per kind of project data.
EXPECTED_REGISTRATIONS = {
    "Requirement",
    "ProjectScoringSettings",
    "CvFile",
    "Candidate",
    "ProjectFactorSettings",
}
# Work stoppers registered with register_work_stopper.
EXPECTED_STOPPERS = {"CvProcessing"}
# Models that mention a project on purpose and are kept: the usage ledger and AI call log.
KEPT_FOR_HISTORY = {"UsageCounter", "CvUsage", "AiCall"}


def url(project, suffix=""):
    return f"/api/company/projects/{project.pk}/{suffix}"


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def make_project(company, person, title="Backend engineer"):
    return Project.objects.create(
        company=company,
        title=title,
        job_description="text",
        reading_model="model",
        created_by=person,
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
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=100000,
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


@pytest.fixture
def isolated_registry():
    removers, stoppers = dict(deletion.DATA_REMOVERS), dict(deletion.WORK_STOPPERS)
    yield
    deletion.DATA_REMOVERS.clear()
    deletion.DATA_REMOVERS.update(removers)
    deletion.WORK_STOPPERS.clear()
    deletion.WORK_STOPPERS.update(stoppers)


class TestEveryKindOfProjectDataIsRegistered:
    def test_the_registered_data_is_exactly_the_expected_list(self):
        assert set(deletion.DATA_REMOVERS) == EXPECTED_REGISTRATIONS

    def test_the_registered_stoppers_are_exactly_the_expected_list(self):
        assert set(deletion.WORK_STOPPERS) == EXPECTED_STOPPERS

    def test_no_model_belonging_to_a_project_is_forgotten(self):
        belonging = {
            model.__name__
            for model in apps.get_models()
            if model is not Project
            and any(
                field.name in ("project", "project_id")
                or (field.is_relation and field.related_model is Project)
                for field in model._meta.get_fields()
            )
        }
        unregistered = belonging - KEPT_FOR_HISTORY - set(deletion.DATA_REMOVERS)
        assert not unregistered, (
            f"Project data not removed by projects/deletion.py: {sorted(unregistered)}. "
            "Register it with register_project_data and add it to EXPECTED_REGISTRATIONS."
        )


class TestDeleting:
    def test_the_owner_deletes_after_typing_the_title(self, company):
        owner, client = sign_in(company)
        project = make_project(company, owner)
        response = client.delete(url(project), {"confirm_title": "Backend engineer"}, format="json")
        assert response.status_code == 204
        assert not Project.objects.filter(pk=project.pk).exists()

    @pytest.mark.parametrize("typed", ["", "backend engineer", "Backend", "Other"])
    def test_a_wrong_title_deletes_nothing(self, company, typed):
        owner, client = sign_in(company)
        project = make_project(company, owner)
        response = client.delete(url(project), {"confirm_title": typed}, format="json")
        assert response.status_code == 400
        assert "confirm_title" in response.json()["error"]["fields"]
        assert Project.objects.filter(pk=project.pk).exists()

    def test_no_title_at_all_deletes_nothing(self, company):
        owner, client = sign_in(company)
        project = make_project(company, owner)
        assert client.delete(url(project)).status_code == 400
        assert Project.objects.filter(pk=project.pk).exists()

    def test_a_member_cannot_delete(self, company):
        owner, _ = sign_in(company)
        project = make_project(company, owner)
        _, member = sign_in(company, role="member")
        response = member.delete(url(project), {"confirm_title": project.title}, format="json")
        assert response.status_code == 403
        assert Project.objects.filter(pk=project.pk).exists()

    def test_an_archived_project_can_be_deleted(self, company):
        owner, client = sign_in(company)
        project = make_project(company, owner)
        Project.objects.filter(pk=project.pk).update(status="archived")
        response = client.delete(url(project), {"confirm_title": project.title}, format="json")
        assert response.status_code == 204

    def test_another_companys_project_is_not_found(self, company):
        stranger = make_company()
        theirs = make_project(stranger, make_company_user(stranger))
        _, client = sign_in(company)
        response = client.delete(url(theirs), {"confirm_title": theirs.title}, format="json")
        assert response.status_code == 404
        assert Project.objects.filter(pk=theirs.pk).exists()

    def test_other_projects_stay(self, company):
        owner, client = sign_in(company)
        gone, kept = make_project(company, owner, "Gone"), make_project(company, owner, "Kept")
        client.delete(url(gone), {"confirm_title": "Gone"}, format="json")
        assert Project.objects.filter(pk=kept.pk).exists()

    def test_the_deletion_is_logged_without_the_title_or_any_name(self, company):
        owner, client = sign_in(company)
        project = make_project(company, owner, "Secret Role Name")
        client.delete(url(project), {"confirm_title": "Secret Role Name"}, format="json")
        entry = ActivityEntry.objects.get(company=company, kind="project_deleted")
        assert entry.target_id == str(project.pk)
        assert entry.details == {}
        assert "Secret Role Name" not in str(entry.__dict__.values())


class TestRegisteredWorkAndData:
    def test_every_registered_piece_runs_with_the_company_and_project(
        self, company, isolated_registry
    ):
        owner, client = sign_in(company)
        project = make_project(company, owner)
        calls = []
        deletion.register_work_stopper("scoring", lambda c, p: calls.append(("stop", c, p)))
        deletion.register_project_data("files", lambda c, p: calls.append(("files", c, p)))
        deletion.register_project_data("results", lambda c, p: calls.append(("results", c, p)))
        client.delete(url(project), {"confirm_title": project.title}, format="json")
        ids = (company.pk, project.pk)
        assert calls == [("stop", *ids), ("files", *ids), ("results", *ids)]

    def test_work_is_stopped_before_anything_is_removed(self, company, isolated_registry):
        owner, client = sign_in(company)
        project = make_project(company, owner)
        order = []
        deletion.register_work_stopper("scoring", lambda c, p: order.append("stopped"))
        deletion.register_project_data("files", lambda c, p: order.append("removed"))
        client.delete(url(project), {"confirm_title": project.title}, format="json")
        assert order == ["stopped", "removed"]

    def test_if_removing_fails_nothing_is_deleted(self, company, isolated_registry):
        owner, client = sign_in(company)
        project = make_project(company, owner)

        def fail(company_id, project_id):
            raise RuntimeError("storage unreachable")

        deletion.register_project_data("files", fail)
        client.raise_request_exception = False
        response = client.delete(url(project), {"confirm_title": project.title}, format="json")
        assert response.status_code == 500
        assert Project.objects.filter(pk=project.pk).exists()
        assert not ActivityEntry.objects.filter(kind="project_deleted").exists()


class TestUsageHistory:
    def test_past_usage_stays_after_the_project_is_deleted(self, company):
        owner, client = sign_in(company)
        project = make_project(company, owner)
        usage.accept_cv(company.pk, CV_ID, project.pk)
        usage.mark_scored(company.pk, CV_ID)
        client.delete(url(project), {"confirm_title": project.title}, format="json")
        assert usage.current_usage(company.pk)["cvs_scored"] == 1


def test_deleting_a_project_removes_its_requirements(company):
    from projects.models import Requirement

    owner, client = sign_in(company)
    project = make_project(company, owner)
    other = make_project(company, owner, "Other")
    for target in (project, other):
        Requirement.objects.create(
            company=company, project=target, position=0, kind="must", text="x", weight=3
        )
    client.delete(url(project), {"confirm_title": project.title}, format="json")
    assert not Requirement.objects.filter(project_id=project.pk).exists()
    assert Requirement.objects.filter(project_id=other.pk).count() == 1


def test_deleting_a_project_removes_its_scoring_settings(company):
    from projects.models import ProjectScoringSettings

    owner, client = sign_in(company)
    project = make_project(company, owner)
    other = make_project(company, owner, "Other")
    for target in (project, other):
        ProjectScoringSettings.objects.create(
            company=company,
            project=target,
            must_weight_percent=70,
            nice_weight_percent=30,
            recommendation_threshold=75,
            top_n=10,
        )
    client.delete(url(project), {"confirm_title": project.title}, format="json")
    assert not ProjectScoringSettings.objects.filter(project_id=project.pk).exists()
    assert ProjectScoringSettings.objects.filter(project_id=other.pk).count() == 1
