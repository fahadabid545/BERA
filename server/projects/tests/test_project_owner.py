import pytest
from rest_framework.test import APIClient

from activity.models import ActivityEntry
from companies.models import CompanyUser
from core.tests.factories import make_company, make_company_user
from projects.models import Project
from projects.tests.helpers import sign_in

pytestmark = pytest.mark.django_db


def change(client, project, owner_id):
    return client.put(
        f"/api/company/projects/{project.pk}/owner/", {"owner_id": owner_id}, format="json"
    )


@pytest.fixture
def teammate(company):
    return make_company_user(company, role="member")


class TestChangeOwner:
    def test_the_owner_hands_the_project_to_a_member(self, owner, project, teammate):
        response = change(owner, project, teammate.pk)
        assert response.status_code == 200 and response.json()["owner_id"] == teammate.pk
        assert Project.objects.get(pk=project.pk).created_by_id == teammate.pk

    def test_it_is_logged_with_who_and_to_whom(self, owner, project, teammate):
        change(owner, project, teammate.pk)
        entry = ActivityEntry.objects.get(kind="project_owner_changed")
        assert entry.target_id == str(project.pk)
        assert entry.details == {"new_owner_name": teammate.name}

    def test_the_project_describes_who_may_change_the_owner(self, owner, project):
        body = owner.get(f"/api/company/projects/{project.pk}/").json()
        assert body["may_change_owner"] is True and body["owner_id"] == project.created_by_id

    def test_a_member_may_not_and_is_told_so(self, company, project, teammate):
        _, member = sign_in(company, role="member")
        assert change(member, project, teammate.pk).status_code == 403
        body = member.get(f"/api/company/projects/{project.pk}/").json()
        assert body["may_change_owner"] is False

    def test_the_current_owner_cannot_be_chosen_again(self, owner, project):
        response = change(owner, project, project.created_by_id)
        assert response.status_code == 400
        assert "owner_id" in response.json()["error"]["fields"]

    def test_a_removed_member_cannot_be_chosen(self, owner, project, teammate):
        CompanyUser.objects.filter(pk=teammate.pk).update(status="removed")
        response = change(owner, project, teammate.pk)
        assert response.status_code == 400 and "owner_id" in response.json()["error"]["fields"]
        assert Project.objects.get(pk=project.pk).created_by_id != teammate.pk

    def test_a_person_of_another_company_is_not_found(self, owner, project):
        stranger = make_company_user(make_company())
        assert change(owner, project, stranger.pk).status_code == 404
        assert not ActivityEntry.objects.filter(kind="project_owner_changed").exists()

    def test_a_missing_or_wrong_owner_is_refused(self, owner, project):
        url = f"/api/company/projects/{project.pk}/owner/"
        assert owner.put(url, {}, format="json").status_code == 400
        assert owner.put(url, {"owner_id": "abc"}, format="json").status_code == 400
        assert owner.put(url, {"owner_id": 0}, format="json").status_code == 400

    def test_another_companys_project_is_not_found(self, project, teammate):
        _, stranger = sign_in(make_company())
        assert change(stranger, project, teammate.pk).status_code == 404

    def test_nobody_signed_in_is_refused(self, project, teammate):
        assert change(APIClient(), project, teammate.pk).status_code == 401
