import pytest
from rest_framework.test import APIClient

from activity.models import ActivityEntry
from core.tests.factories import make_company
from projects.models import Project
from projects.tests.helpers import sign_in

pytestmark = pytest.mark.django_db


def pause(client, project, paused):
    return client.put(
        f"/api/company/projects/{project.pk}/uploads/", {"paused": paused}, format="json"
    )


class TestPauseUploads:
    def test_pausing_and_resuming_show_in_the_project(self, owner, project):
        assert owner.get(f"/api/company/projects/{project.pk}/").json()["uploads_paused"] is False
        assert pause(owner, project, True).json()["uploads_paused"] is True
        assert Project.objects.get(pk=project.pk).uploads_paused is True
        assert pause(owner, project, False).json()["uploads_paused"] is False

    def test_each_change_is_logged_and_a_repeat_is_not(self, owner, project):
        pause(owner, project, True)
        pause(owner, project, True)
        pause(owner, project, False)
        kinds = list(
            ActivityEntry.objects.filter(kind="setting_changed")
            .order_by("created_at")
            .values_list("details", flat=True)
        )
        assert kinds == [{"setting": "uploads_paused"}, {"setting": "uploads_resumed"}]

    def test_a_member_may_pause(self, company, project):
        _, member = sign_in(company, role="member")
        assert pause(member, project, True).status_code == 200

    def test_an_archived_project_cannot_be_changed(self, owner, project):
        Project.objects.filter(pk=project.pk).update(status="archived")
        response = pause(owner, project, True)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_archived"

    @pytest.mark.parametrize("body", [{}, {"paused": "maybe"}, {"paused": True, "extra": 1}])
    def test_a_wrong_body_is_refused(self, owner, project, body):
        response = owner.put(f"/api/company/projects/{project.pk}/uploads/", body, format="json")
        assert response.status_code == 400

    def test_another_companys_project_is_not_found(self, project):
        _, stranger = sign_in(make_company())
        assert pause(stranger, project, True).status_code == 404

    def test_nobody_signed_in_is_refused(self, project):
        assert pause(APIClient(), project, True).status_code == 401
