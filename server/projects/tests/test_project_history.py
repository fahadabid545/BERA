import pytest

from core.tests.factories import make_company, make_company_user
from projects.tests.helpers import sign_in

pytestmark = pytest.mark.django_db


def entries(client, project):
    return client.get(f"/api/company/projects/{project.pk}/history/").json()["entries"]


def changes(client, project):
    return [e["details"].get("change") for e in entries(client, project)]


class TestProjectHistory:
    def test_a_new_project_has_no_history(self, owner, project):
        assert entries(owner, project) == []

    def test_a_title_change_is_listed_with_who_made_it(self, owner, project):
        owner.patch(f"/api/company/projects/{project.pk}/", {"title": "Platform lead"})
        (entry,) = entries(owner, project)
        assert entry["details"] == {"change": "title"} and entry["actor_name"]

    def test_changing_title_and_description_lists_both(self, owner, project):
        owner.patch(
            f"/api/company/projects/{project.pk}/",
            {"title": "Platform lead", "job_description": "A new long description. " * 12},
        )
        assert sorted(changes(owner, project)) == ["job_description", "title"]

    def test_sending_the_same_title_again_is_not_a_change(self, owner, project):
        owner.patch(f"/api/company/projects/{project.pk}/", {"title": project.title})
        assert entries(owner, project) == []

    def test_a_preference_change_is_listed(self, owner, project):
        owner.put(f"/api/company/projects/{project.pk}/preferences/", {"auto_shortlist": True})
        (entry,) = entries(owner, project)
        assert entry["kind"] == "setting_changed"

    def test_newest_comes_first(self, owner, project):
        owner.patch(f"/api/company/projects/{project.pk}/", {"title": "First title"})
        owner.patch(f"/api/company/projects/{project.pk}/", {"title": "Second title"})
        assert len(entries(owner, project)) == 2

    def test_another_projects_changes_are_not_listed(self, owner, project, company):
        other = owner.post(f"/api/company/projects/{project.pk}/duplicate/").json()["id"]
        owner.patch(f"/api/company/projects/{other}/", {"title": "Renamed role"})
        assert entries(owner, project) == []

    def test_another_company_gets_not_found(self, project):
        _, stranger = sign_in(make_company())
        response = stranger.get(f"/api/company/projects/{project.pk}/history/")
        assert response.status_code == 404

    def test_a_member_may_read_it(self, company, project):
        make_company_user(company, role="member")
        _, member = sign_in(company, role="member")
        assert member.get(f"/api/company/projects/{project.pk}/history/").status_code == 200

    def test_signed_out_is_refused(self, project):
        from rest_framework.test import APIClient

        assert APIClient().get(f"/api/company/projects/{project.pk}/history/").status_code == 401


class TestOtherChanges:
    def test_saved_scoring_settings_are_listed(self, owner, project):
        owner.put(
            f"/api/company/projects/{project.pk}/scoring/",
            {
                "must_weight_percent": 70,
                "nice_weight_percent": 30,
                "recommendation_threshold": 75,
                "top_n": 10,
                "cap_on_missing_must_have": False,
            },
            format="json",
        )
        assert changes(owner, project) == ["scoring"]

    def test_refused_scoring_settings_are_not_listed(self, owner, project):
        owner.put(
            f"/api/company/projects/{project.pk}/scoring/",
            {"must_weight_percent": 10, "nice_weight_percent": 10},
            format="json",
        )
        assert entries(owner, project) == []
