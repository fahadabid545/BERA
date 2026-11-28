import pytest
from rest_framework.test import APIClient

from activity.models import ActivityEntry
from core.tests.factories import make_company
from projects.models import Project
from projects.tests.helpers import sign_in

pytestmark = pytest.mark.django_db


def url(project):
    return f"/api/company/projects/{project.pk}/preferences/"


def save(client, project, **body):
    return client.put(url(project), body, format="json")


class TestPreferences:
    def test_the_defaults_are_read(self, owner, project):
        assert owner.get(url(project)).json() == {
            "hide_contact_by_default": False,
            "auto_shortlist": False,
            "auto_reject_below": None,
            "labels": [],
        }

    def test_the_project_carries_them_too(self, owner, project):
        body = owner.get(f"/api/company/projects/{project.pk}/").json()
        assert body["preferences"]["hide_contact_by_default"] is False

    def test_saving_changes_only_what_is_sent_and_logs_it(self, owner, project):
        response = save(owner, project, hide_contact_by_default=True)
        assert response.status_code == 200 and response.json()["hide_contact_by_default"] is True
        assert Project.objects.get(pk=project.pk).hide_contact_by_default is True
        entry = ActivityEntry.objects.get(kind="setting_changed")
        assert entry.details == {"setting": "hide_contact_by_default"}

    def test_saving_the_same_value_again_logs_nothing(self, owner, project):
        save(owner, project, hide_contact_by_default=False)
        assert not ActivityEntry.objects.filter(kind="setting_changed").exists()

    def test_the_intake_rules_are_saved_and_the_limit_can_be_cleared(self, owner, project):
        body = save(owner, project, auto_shortlist=True, auto_reject_below=35).json()
        assert (body["auto_shortlist"], body["auto_reject_below"]) == (True, 35)
        assert save(owner, project, auto_reject_below=None).json()["auto_reject_below"] is None
        settings = list(
            ActivityEntry.objects.filter(kind="setting_changed")
            .order_by("created_at")
            .values_list("details__setting", flat=True)
        )
        assert settings == ["auto_shortlist", "auto_reject_below", "auto_reject_below"]

    @pytest.mark.parametrize("limit", [-1, 101, "high", 2.5])
    def test_a_limit_outside_zero_to_one_hundred_is_refused(self, owner, project, limit):
        response = save(owner, project, auto_reject_below=limit)
        assert response.status_code == 400
        assert "auto_reject_below" in response.json()["error"]["fields"]

    def test_an_empty_save_changes_nothing(self, owner, project):
        assert save(owner, project).status_code == 200

    @pytest.mark.parametrize(
        "body",
        [{"hide_contact_by_default": "maybe"}, {"unknown": True}, {"hide_contact_by_default": []}],
    )
    def test_a_wrong_body_is_refused(self, owner, project, body):
        assert save(owner, project, **body).status_code == 400

    def test_an_archived_project_cannot_be_changed(self, owner, project):
        Project.objects.filter(pk=project.pk).update(status="archived")
        response = save(owner, project, hide_contact_by_default=True)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_archived"

    def test_a_member_may_save(self, company, project):
        _, member = sign_in(company, role="member")
        assert save(member, project, hide_contact_by_default=True).status_code == 200

    def test_another_companys_project_is_not_found(self, project):
        _, stranger = sign_in(make_company())
        assert save(stranger, project, hide_contact_by_default=True).status_code == 404

    def test_nobody_signed_in_is_refused(self, project):
        assert save(APIClient(), project, hide_contact_by_default=True).status_code == 401
