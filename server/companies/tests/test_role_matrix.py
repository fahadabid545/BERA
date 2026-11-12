import pytest
from rest_framework.test import APIClient

from companies.models import Company, CompanyUser
from companies.role_matrix import ROLES_ALLOWED, roles_allowed
from core.tests.factories import make_company, make_company_user, start_session_for
from signin import service

pytestmark = [pytest.mark.urls("companies.tests.urls_for_roles"), pytest.mark.django_db]

# The matrix as the ticket states it, written out again here on purpose: changing a rule in
# role_matrix.py must also change this list, so a rule never changes by accident.
MEMBER_MAY = [
    "project.create",
    "project.edit",
    "project.archive",
    "cv.upload",
    "cv.download",
    "candidate.view",
    "candidate.change_stage",
    "candidate.write_note",
    "candidate.delete",
    "report.download",
    "report.share",
]
MEMBER_MAY_NOT = [
    "activity.view",
    "team.view",
    "team.invite",
    "team.remove",
    "team.transfer_ownership",
    "billing.view",
    "settings.change",
    "advanced.open",
    "project.delete",
    "company.delete",
]


def person(role, company=None):
    company = company or make_company()
    return make_company_user(company, role=role), company


def client_for(account):
    issued = start_session_for(
        user_id=account.pk, role=account.role, company_id=account.company_id, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def do(client, action):
    return client.post(f"/api/actions/{action}/")


def test_the_test_list_covers_every_action_of_the_matrix_exactly():
    assert sorted(MEMBER_MAY + MEMBER_MAY_NOT) == sorted(ROLES_ALLOWED)


@pytest.mark.parametrize("action", sorted(ROLES_ALLOWED))
def test_an_owner_can_do_everything(action):
    owner, _ = person("owner")
    response = do(client_for(owner), action)
    assert (response.status_code, response.json()) == (200, {"done": action})


@pytest.mark.parametrize("action", MEMBER_MAY)
def test_a_member_can_do_what_members_may(action):
    member, _ = person("member")
    assert do(client_for(member), action).status_code == 200


@pytest.mark.parametrize("action", MEMBER_MAY_NOT)
def test_a_member_is_refused_what_only_owners_may(action):
    member, _ = person("member")
    response = do(client_for(member), action)
    assert (response.status_code, response.json()["error"]["code"]) == (403, "not_allowed")


@pytest.mark.parametrize("action", sorted(ROLES_ALLOWED))
def test_a_visitor_and_an_admin_sign_in_are_refused_everything(action):
    assert do(APIClient(), action).status_code == 401
    admin = start_session_for(user_id=1, role="super", company_id=None, kind="admin")
    admin_client = APIClient(HTTP_AUTHORIZATION=f"Bearer {admin.access_token}")
    assert do(admin_client, action).status_code == 401


def test_both_roles_can_delete_a_candidate_but_only_an_owner_deletes_a_project():
    assert roles_allowed("candidate.delete") == {"owner", "member"}
    assert roles_allowed("project.delete") == {"owner"}


def test_an_unknown_action_fails_loudly_instead_of_allowing_anything():
    with pytest.raises(KeyError):
        roles_allowed("project.make_everything_free")


class TestChangesApplyAtOnce:
    def test_promoting_a_member_works_without_logging_in_again(self):
        member, _ = person("member")
        client = client_for(member)
        assert do(client, "team.invite").status_code == 403
        CompanyUser.objects.filter(pk=member.pk).update(role="owner")
        assert do(client, "team.invite").status_code == 200

    def test_demoting_an_owner_takes_the_rights_away_with_the_same_token(self):
        owner, company = person("owner")
        CompanyUser.objects.create(
            company=company, name="Fake", email="x1@example.test", role="member"
        )
        client = client_for(owner)
        assert do(client, "billing.view").status_code == 200
        CompanyUser.objects.filter(pk=owner.pk).update(role="member")
        assert do(client, "billing.view").status_code == 403

    def test_a_renewed_token_carries_the_current_role(self):
        member, _ = person("member")
        issued = start_session_for(
            user_id=member.pk, role="member", company_id=member.company_id, kind="company"
        )
        CompanyUser.objects.filter(pk=member.pk).update(role="owner")
        renewed = service.refresh_session(issued.refresh_token, "company")
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {renewed.access_token}")
        assert do(client, "team.invite").status_code == 200

    def test_a_forged_role_in_a_token_does_nothing(self):
        # Even a validly signed token that claims a bigger role cannot raise the stored role.
        from signin.tests.helpers import forge

        member, _ = person("member")
        issued = start_session_for(
            user_id=member.pk, role="member", company_id=member.company_id, kind="company"
        )
        token = forge(
            sub=str(member.pk), sid=issued.session_id, cid=member.company_id, role="owner"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert do(client, "team.invite").status_code == 403


class TestEveryRequestChecksThatPersonAndCompanyAreActive:
    def test_suspending_the_company_stops_working_tokens_at_once(self):
        owner, company = person("owner")
        client = client_for(owner)
        assert do(client, "project.create").status_code == 200
        Company.objects.filter(pk=company.pk).update(status="suspended")  # skips signals
        response = do(client, "project.create")
        assert (response.status_code, response.json()["error"]["code"]) == (401, "not_signed_in")

    def test_suspending_through_the_app_also_ends_the_sessions(self):
        from signin.models import Session

        owner, company = person("owner")
        client_for(owner)
        company.status = "suspended"
        company.save()
        assert Session.objects.filter(company_id=company.pk, status="active").count() == 0
        company.status = "active"
        company.save()
        assert Session.objects.filter(status="active").count() == 0  # old tokens stay dead

    def test_a_suspended_company_cannot_renew_a_token(self):
        from rest_framework.exceptions import NotAuthenticated

        owner, company = person("owner")
        issued = start_session_for(
            user_id=owner.pk, role="owner", company_id=company.pk, kind="company"
        )
        Company.objects.filter(pk=company.pk).update(status="suspended")
        with pytest.raises(NotAuthenticated):
            service.refresh_session(issued.refresh_token, "company")

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_blocking_or_removing_a_person_stops_their_tokens_at_once(self, status):
        member, company = person("member")
        client = client_for(member)
        CompanyUser.objects.filter(pk=member.pk).update(status=status)
        assert do(client, "project.create").status_code == 401

    def test_a_person_who_moved_to_another_company_cannot_use_the_old_session(self):
        member, _ = person("member")
        client = client_for(member)
        CompanyUser.objects.filter(pk=member.pk).update(company=make_company())
        assert do(client, "project.create").status_code == 401

    def test_other_people_of_a_suspended_company_are_stopped_too(self):
        owner, company = person("owner")
        member, _ = person("member", company)
        member_client = client_for(member)
        Company.objects.filter(pk=company.pk).update(status="suspended")
        assert do(member_client, "project.create").status_code == 401

    def test_other_companies_are_not_affected(self):
        owner, company = person("owner")
        other_owner, _ = person("owner")
        other_client = client_for(other_owner)
        Company.objects.filter(pk=company.pk).update(status="suspended")
        assert do(other_client, "project.create").status_code == 200
