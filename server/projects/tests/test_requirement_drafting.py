import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai import client
from ai.client import AiUnavailable
from core.errors import AppError
from cvs import processing
from cvs.models import CvFile
from projects import drafting
from projects import requirements as requirement_service
from projects.models import Project, Requirement
from projects.tests.helpers import LONG_TEXT, sign_in
from projects.tests.test_requirement_extraction import answer_with, good

pytestmark = pytest.mark.django_db


def state(project):
    return Project.objects.get(pk=project.pk).requirements_status


def stored(project):
    return list(
        Requirement.objects.filter(project=project)
        .order_by("position")
        .values_list("kind", "text", "weight")
    )


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(drafting, "async_task", lambda job, *args: calls.append((job, args)))
    return calls


@pytest.fixture
def drafting_project(project):
    Project.objects.filter(pk=project.pk).update(requirements_status="drafting")
    return project


class TestCreation:
    def test_a_new_project_is_drafting_and_the_job_is_queued_after_it_is_saved(
        self, owner, queued, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = owner.post(
                "/api/company/projects/", {"title": "New role", "job_description": LONG_TEXT}
            )
        assert response.status_code == 201, response.content
        created = Project.objects.get(pk=response.json()["id"])
        assert created.requirements_status == "drafting"
        assert queued == [(drafting.DRAFT_JOB, (str(created.pk),))]

    def test_existing_projects_count_as_confirmed(self, project):
        assert state(project) == "confirmed"


class TestDraftingJob:
    def test_stores_the_ai_requirements_with_weights_as_a_draft(
        self, drafting_project, monkeypatch
    ):
        answer_with(monkeypatch, good(("must", "Python", 5), ("nice", "Docker", 2)))
        drafting.draft_requirements(str(drafting_project.pk))
        assert stored(drafting_project) == [("must", "Python", 5), ("nice", "Docker", 2)]
        assert state(drafting_project) == "draft"
        assert Project.objects.get(pk=drafting_project.pk).requirements_notice == ""

    def test_an_unavailable_ai_leaves_an_empty_draft_with_a_plain_notice(
        self, drafting_project, monkeypatch
    ):
        monkeypatch.setattr(client, "_send", lambda **_: (_ for _ in ()).throw(AiUnavailable("x")))
        drafting.draft_requirements(str(drafting_project.pk))
        assert stored(drafting_project) == [] and state(drafting_project) == "draft"
        assert (
            "enter them yourself" in Project.objects.get(pk=drafting_project.pk).requirements_notice
        )

    def test_a_short_description_warning_becomes_the_notice(self, drafting_project, monkeypatch):
        Project.objects.filter(pk=drafting_project.pk).update(job_description="Python dev")
        answer_with(monkeypatch, good(("must", "Python")))
        drafting.draft_requirements(str(drafting_project.pk))
        assert "short" in Project.objects.get(pk=drafting_project.pk).requirements_notice

    def test_an_unusable_answer_leaves_an_empty_draft(self, drafting_project, monkeypatch):
        answer_with(monkeypatch, "not json")
        drafting.draft_requirements(str(drafting_project.pk))
        assert stored(drafting_project) == [] and state(drafting_project) == "draft"

    def test_a_blocked_plan_leaves_an_empty_draft_with_the_reason(
        self, drafting_project, monkeypatch
    ):
        def blocked(*_args, **_kwargs):
            raise AppError("ai_blocked", "AI is not part of this plan.", status_code=403)

        monkeypatch.setattr(drafting, "suggest_requirements", blocked)
        drafting.draft_requirements(str(drafting_project.pk))
        notice = Project.objects.get(pk=drafting_project.pk).requirements_notice
        assert notice == "AI is not part of this plan." and state(drafting_project) == "draft"

    def test_an_unexpected_failure_still_unblocks_the_person_and_is_reported(
        self, drafting_project, monkeypatch
    ):
        def broken(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafting, "suggest_requirements", broken)
        with pytest.raises(AppError) as raised:
            drafting.draft_requirements(str(drafting_project.pk))
        assert raised.value.code == "job_failed"
        assert state(drafting_project) == "draft" and stored(drafting_project) == []

    def test_a_list_the_person_confirmed_meanwhile_is_not_overwritten(
        self, drafting_project, monkeypatch
    ):
        def person_saves_first(project):
            Requirement.objects.create(
                company_id=project.company_id, project=project, position=0,
                kind="must", text="Mine", weight=4,
            )  # fmt: skip
            Project.objects.filter(pk=project.pk).update(requirements_status="confirmed")
            return {
                "requirements": [{"kind": "must", "text": "AI", "weight": 1}],
                "warnings": [], "fallback": False, "message": "",
            }  # fmt: skip

        monkeypatch.setattr(drafting, "suggest_requirements", person_saves_first)
        drafting.draft_requirements(str(drafting_project.pk))
        assert stored(drafting_project) == [("must", "Mine", 4)]
        assert state(drafting_project) == "confirmed"

    def test_a_repeated_job_does_nothing(self, project, monkeypatch):
        answer_with(monkeypatch, good(("must", "Python")))
        drafting.draft_requirements(str(project.pk))  # confirmed project: not drafting
        assert stored(project) == []

    def test_a_project_that_is_gone_is_ignored(self):
        drafting.draft_requirements("00000000-0000-0000-0000-000000000000")


class TestConfirming:
    def make_draft(self, project, with_item=True):
        Project.objects.filter(pk=project.pk).update(requirements_status="draft")
        if with_item:
            Requirement.objects.create(
                company_id=project.company_id, project=project, position=0,
                kind="must", text="Python", weight=3,
            )  # fmt: skip

    def test_confirming_unlocks_the_project_and_wakes_the_workers(
        self, owner, project, monkeypatch
    ):
        self.make_draft(project)
        woken = []
        monkeypatch.setattr(requirement_service, "wake_workers", woken.append)
        response = owner.post(f"/api/company/projects/{project.pk}/requirements/confirm/")
        assert response.status_code == 200 and response.json()["status"] == "confirmed"
        assert state(project) == "confirmed" and woken == [0]

    def test_an_empty_list_cannot_be_confirmed(self, owner, project):
        self.make_draft(project, with_item=False)
        response = owner.post(f"/api/company/projects/{project.pk}/requirements/confirm/")
        assert response.status_code == 409 and state(project) == "draft"
        assert response.json()["error"]["code"] == "requirements_needed"

    def test_saving_the_list_confirms_it(self, owner, project):
        self.make_draft(project, with_item=False)
        response = owner.put(
            f"/api/company/projects/{project.pk}/requirements/",
            {"requirements": [{"kind": "must", "text": "Python", "weight": 5}]},
            format="json",
        )
        assert response.status_code == 200 and response.json()["status"] == "confirmed"
        assert stored(project) == [("must", "Python", 5)]

    def test_saving_while_the_ai_is_still_reading_confirms_the_persons_own_list(
        self, owner, drafting_project
    ):
        owner.put(
            f"/api/company/projects/{drafting_project.pk}/requirements/",
            {"requirements": [{"kind": "must", "text": "Mine", "weight": 2}]},
            format="json",
        )
        assert state(drafting_project) == "confirmed"

    def test_the_requirements_page_says_where_the_list_stands(self, owner, project):
        self.make_draft(project)
        Project.objects.filter(pk=project.pk).update(requirements_notice="Check these.")
        body = owner.get(f"/api/company/projects/{project.pk}/requirements/").json()
        assert (body["status"], body["notice"]) == ("draft", "Check these.")

    def test_nobody_signed_in_is_refused(self, project):
        self.make_draft(project)
        response = APIClient().post(f"/api/company/projects/{project.pk}/requirements/confirm/")
        assert response.status_code == 401 and state(project) == "draft"

    def test_another_companys_project_is_not_found(self, project):
        from core.tests.factories import make_company

        _, stranger = sign_in(make_company())
        response = stranger.post(f"/api/company/projects/{project.pk}/requirements/confirm/")
        assert response.status_code == 404


class TestReading:
    def test_a_draft_can_be_read_again_in_the_background(
        self, owner, project, queued, django_capture_on_commit_callbacks
    ):
        Project.objects.filter(pk=project.pk).update(requirements_status="draft")
        with django_capture_on_commit_callbacks(execute=True):
            response = owner.post(f"/api/company/projects/{project.pk}/requirements/reread/")
        assert response.status_code == 202 and response.json()["status"] == "drafting"
        assert queued == [(drafting.DRAFT_JOB, (str(project.pk),))]

    @pytest.mark.parametrize("current", ["drafting", "confirmed"])
    def test_only_a_draft_can_be_read_again(self, owner, project, queued, current):
        Project.objects.filter(pk=project.pk).update(requirements_status=current)
        response = owner.post(f"/api/company/projects/{project.pk}/requirements/reread/")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "requirements_not_a_draft"
        assert queued == [] and state(project) == current

    def test_the_new_reading_replaces_the_old_draft(self, owner, project, queued, monkeypatch):
        Project.objects.filter(pk=project.pk).update(requirements_status="draft")
        Requirement.objects.create(
            company_id=project.company_id, project=project, position=0,
            kind="must", text="Old", weight=3,
        )  # fmt: skip
        owner.post(f"/api/company/projects/{project.pk}/requirements/reread/")
        answer_with(monkeypatch, good(("nice", "New", 1)))
        drafting.draft_requirements(str(project.pk))
        assert stored(project) == [("nice", "New", 1)]


class TestProcessingWaits:
    def add_cv(self, project, person):
        return CvFile.objects.create(
            company=project.company, project=project, original_name="a.pdf", file_type="pdf",
            size_bytes=1, storage_key=f"k/{project.pk}", content_hash="h", uploaded_by=person,
            status="waiting", next_attempt_at=timezone.now(),
        )  # fmt: skip

    @pytest.mark.parametrize("held", ["drafting", "draft"])
    def test_cvs_wait_until_the_requirements_are_confirmed(self, project, held):
        item = self.add_cv(project, project.created_by)
        Project.objects.filter(pk=project.pk).update(requirements_status=held)
        assert processing.claim_next() is None
        assert not processing.due(timezone.now()).exists()
        item.refresh_from_db()
        assert item.status == "waiting" and item.attempts == 0

    def test_they_are_taken_once_confirmed(self, project):
        item = self.add_cv(project, project.created_by)
        assert processing.due(timezone.now()).filter(pk=item.pk).exists()
        assert processing.claim_next().pk == item.pk
