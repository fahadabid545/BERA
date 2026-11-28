import pytest
from rest_framework.test import APIClient

from core.tests.factories import make_company
from cvs.models import CvFile
from cvs.tests.test_ai_reading import set_setting
from plans.models import Plan
from projects import drafting
from projects.models import (
    Project,
    ProjectFactorSettings,
    ProjectScoringSettings,
    Requirement,
)
from projects.tests.helpers import sign_in

pytestmark = pytest.mark.django_db


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(drafting, "async_task", lambda job, *args: calls.append(job))
    return calls


def duplicate(client, project):
    return client.post(f"/api/company/projects/{project.pk}/duplicate/")


@pytest.fixture
def configured(project):
    for position, (kind, text, weight) in enumerate([("must", "Python", 5), ("nice", "Docker", 2)]):
        Requirement.objects.create(
            company_id=project.company_id, project=project, position=position,
            kind=kind, text=text, weight=weight,
        )  # fmt: skip
    ProjectScoringSettings.objects.create(
        project=project, company_id=project.company_id, must_weight_percent=70,
        nice_weight_percent=30, recommendation_threshold=65, top_n=4,
        cap_on_missing_must_have=True,
    )  # fmt: skip
    ProjectFactorSettings.objects.create(
        project=project, company_id=project.company_id, required_years=4,
        required_education="bachelor", seniority="senior",
        factors={"experience": {"enabled": True, "weight": 20}},
    )  # fmt: skip
    return project


class TestDuplicate:
    def test_copies_the_description_requirements_and_settings(self, owner, configured, queued):
        response = duplicate(owner, configured)
        assert response.status_code == 201, response.content
        copy = Project.objects.get(pk=response.json()["id"])
        assert copy.pk != configured.pk and copy.job_description == configured.job_description
        assert list(
            Requirement.objects.filter(project=copy)
            .order_by("position")
            .values_list("kind", "text", "weight", "position")
        ) == [("must", "Python", 5, 0), ("nice", "Docker", 2, 1)]
        scoring = ProjectScoringSettings.objects.get(project=copy)
        assert (scoring.must_weight_percent, scoring.top_n, scoring.cap_on_missing_must_have) == (
            70, 4, True,
        )  # fmt: skip
        factors = ProjectFactorSettings.objects.get(project=copy)
        assert (factors.required_years, factors.seniority) == (4, "senior")
        assert factors.factors == {"experience": {"enabled": True, "weight": 20}}

    def test_the_copy_is_confirmed_and_the_ai_is_not_asked_again(self, owner, configured, queued):
        copy = Project.objects.get(pk=duplicate(owner, configured).json()["id"])
        assert copy.requirements_status == "confirmed" and queued == []

    def test_the_copy_has_a_marked_title_and_no_cvs(self, owner, configured, company):
        CvFile.objects.create(
            company=company, project=configured, original_name="a.pdf", file_type="pdf",
            size_bytes=1, storage_key="k/a", content_hash="h", uploaded_by=configured.created_by,
        )  # fmt: skip
        copy = Project.objects.get(pk=duplicate(owner, configured).json()["id"])
        assert copy.title == "Backend engineer (copy)"
        assert CvFile.objects.filter(project=copy).count() == 0

    def test_a_long_title_is_cut_so_the_copy_still_fits(self, owner, project):
        set_setting("projects.title_max_length", 20)
        Project.objects.filter(pk=project.pk).update(title="a" * 20)
        copy = Project.objects.get(pk=duplicate(owner, project).json()["id"])
        assert len(copy.title) == 20 and copy.title.endswith(" (copy)")

    def test_the_original_is_left_alone(self, owner, configured):
        before = Requirement.objects.filter(project=configured).count()
        duplicate(owner, configured)
        assert Requirement.objects.filter(project=configured).count() == before
        assert Project.objects.get(pk=configured.pk).title == "Backend engineer"

    def test_a_project_without_requirements_or_settings_copies_cleanly(self, owner, project):
        copy = Project.objects.get(pk=duplicate(owner, project).json()["id"])
        assert Requirement.objects.filter(project=copy).count() == 0

    def test_an_archived_project_can_be_copied(self, owner, project):
        Project.objects.filter(pk=project.pk).update(status="archived")
        copy = Project.objects.get(pk=duplicate(owner, project).json()["id"])
        assert copy.status == "active"

    def test_a_draft_that_was_still_being_read_is_copied_as_a_draft(self, owner, project):
        Project.objects.filter(pk=project.pk).update(requirements_status="drafting")
        copy = Project.objects.get(pk=duplicate(owner, project).json()["id"])
        assert copy.requirements_status == "draft"

    def test_the_plans_project_limit_applies(self, owner, project):
        Plan.objects.all().update(max_projects=1)
        response = duplicate(owner, project)
        assert response.status_code == 409
        assert Project.objects.count() == 1

    def test_a_member_may_duplicate(self, company, project):
        _, member = sign_in(company, role="member")
        assert duplicate(member, project).status_code == 201

    def test_another_companys_project_is_not_found(self, project):
        _, stranger = sign_in(make_company())
        assert duplicate(stranger, project).status_code == 404

    def test_nobody_signed_in_is_refused(self, project):
        assert duplicate(APIClient(), project).status_code == 401

    def test_a_failure_halfway_leaves_no_half_copy(self, owner, configured, monkeypatch):
        from projects import duplication

        def broken(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(duplication.Requirement.objects, "bulk_create", broken)
        with pytest.raises(RuntimeError):
            duplication.duplicate_project(configured.created_by, configured)
        assert Project.objects.count() == 1
