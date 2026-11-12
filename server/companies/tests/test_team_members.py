import pytest
from rest_framework.test import APIClient

from activity.models import ActivityEntry
from audit.models import AuditEvent
from companies.models import CompanyUser
from companies.tests.test_invites import client_of, invite, team
from core.tests.factories import make_company, make_company_user
from signin.models import Session
from twostep.tests.helpers import PASSWORD

MEMBERS = "/api/company/team/members/"
TRANSFER = "/api/company/team/transfer-ownership/"
pytestmark = pytest.mark.django_db


@pytest.fixture
def company_with_team():
    company, owner = team()
    owner.set_password(PASSWORD)
    owner.save()
    member = make_company_user(company, role="member", name="Fake Member", email_verified=True)
    return company, owner, member


def remove(client, member):
    return client.delete(f"{MEMBERS}{member.pk}/")


def transfer(client, member_id, password=PASSWORD):
    return client.post(TRANSFER, {"member_id": member_id, "password": password}, format="json")


def owners_of(company):
    return CompanyUser.objects.filter(company=company, role="owner", status="active")


class TestTheTeamList:
    def test_it_lists_name_email_role_and_status(self, company_with_team):
        company, owner, member = company_with_team
        rows = client_of(owner).get(MEMBERS).json()
        assert {row["id"]: row for row in rows}[member.pk] == {
            "id": member.pk,
            "name": "Fake Member",
            "email": member.email,
            "role": "member",
            "status": "active",
        }
        assert [row["role"] for row in rows].count("owner") == 1

    def test_blocked_people_are_listed_and_removed_people_are_not(self, company_with_team):
        company, owner, member = company_with_team
        blocked = make_company_user(company, role="member", status="blocked")
        gone = make_company_user(company, role="member", status="removed")
        rows = {row["id"]: row for row in client_of(owner).get(MEMBERS).json()}
        assert rows[blocked.pk]["status"] == "blocked" and gone.pk not in rows

    def test_only_the_own_company_is_listed(self, company_with_team):
        company, owner, member = company_with_team
        _, other_owner = team(company=make_company(name="Fake Other Ltd"))
        ids = {row["id"] for row in client_of(owner).get(MEMBERS).json()}
        assert other_owner.pk not in ids

    def test_pending_invitations_come_from_their_own_list(self, company_with_team):
        _, owner, _ = company_with_team
        client = client_of(owner)
        invite(client)
        assert len(client.get("/api/company/team/invites/").json()) == 1

    def test_members_and_visitors_cannot_read_it(self, company_with_team):
        _, owner, member = company_with_team
        assert client_of(member).get(MEMBERS).status_code == 403
        assert APIClient().get(MEMBERS).status_code == 401


class TestRemovingAMember:
    def test_the_member_is_removed_and_their_sessions_end_at_once(self, company_with_team):
        company, owner, member = company_with_team
        member_client = client_of(member)
        assert member_client.get("/api/auth/company/me/").status_code == 200
        assert remove(client_of(owner), member).status_code == 204
        member.refresh_from_db()
        assert member.status == "removed"
        assert member_client.get("/api/auth/company/me/").status_code == 401
        assert not Session.objects.filter(
            user_id=member.pk, kind="company", status="active"
        ).exists()

    def test_a_removed_member_cannot_log_in_again(self, company_with_team):
        _, owner, member = company_with_team
        member.set_password(PASSWORD)
        member.save()
        remove(client_of(owner), member)
        response = APIClient(REMOTE_ADDR="203.0.113.81").post(
            "/api/auth/company/login/", {"email": member.email, "password": PASSWORD}, format="json"
        )
        assert response.status_code == 400

    def test_their_work_stays_with_the_company_and_the_log_keeps_their_name(
        self, company_with_team
    ):
        from activity import service as activity

        company, owner, member = company_with_team
        activity.record("upload", company_id=company.pk, actor=member)
        remove(client_of(owner), member)
        assert CompanyUser.objects.filter(pk=member.pk).exists()  # the person's row stays
        names = [
            e["actor_name"]
            for e in client_of(owner).get("/api/company/activity/").json()["entries"]
        ]
        assert "Fake Member" in names
        assert ActivityEntry.objects.filter(kind="upload", actor_name="Fake Member").count() == 1

    def test_it_is_logged_in_the_audit_log_and_the_activity_log(self, company_with_team):
        company, owner, member = company_with_team
        remove(client_of(owner), member)
        audit = AuditEvent.objects.get(kind="team.member_removed")
        assert (audit.actor_id, audit.target_id, audit.company_id) == (
            owner.pk,
            str(member.pk),
            company.pk,
        )
        entry = ActivityEntry.objects.get(kind="member_removed")
        assert (entry.actor_name, entry.company_id) == (owner.name, company.pk)
        assert entry.details == {"removed_name": "Fake Member"}

    def test_the_owner_cannot_be_removed_not_even_by_themselves(self, company_with_team):
        company, owner, _ = company_with_team
        response = remove(client_of(owner), owner)
        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "owner_cannot_be_removed",
        )
        owner.refresh_from_db()
        assert owner.status == "active" and owners_of(company).count() == 1
        assert not AuditEvent.objects.filter(kind="team.member_removed").exists()

    def test_removing_twice_is_refused(self, company_with_team):
        _, owner, member = company_with_team
        client = client_of(owner)
        remove(client, member)
        assert remove(client, member).json()["error"]["code"] == "already_removed"

    def test_a_blocked_member_can_be_removed(self, company_with_team):
        company, owner, _ = company_with_team
        blocked = make_company_user(company, role="member", status="blocked")
        assert remove(client_of(owner), blocked).status_code == 204

    def test_the_seat_is_freed(self, company_with_team):
        company, owner, member = company_with_team
        make_company_user(company, role="member")  # three accounts: the limit
        client = client_of(owner)
        assert invite(client).status_code == 409
        remove(client, member)
        assert invite(client).status_code == 201

    def test_someone_of_another_company_or_unknown_is_not_found(self, company_with_team):
        _, owner, _ = company_with_team
        _, other_owner = team(company=make_company(name="Fake Other Ltd"))
        other_member = make_company_user(other_owner.company, role="member")
        client = client_of(owner)
        for target in (other_member.pk, 999999, "abc", "1; DROP"):
            assert client.delete(f"{MEMBERS}{target}/").status_code == 404
        other_member.refresh_from_db()
        assert other_member.status == "active"

    def test_a_member_cannot_remove_anyone(self, company_with_team):
        company, owner, member = company_with_team
        third = make_company_user(company, role="member")
        assert remove(client_of(member), third).status_code == 403
        third.refresh_from_db()
        assert third.status == "active"


class TestHandingTheCompanyOver:
    def test_the_owner_and_the_member_swap_roles_at_once(self, company_with_team):
        company, owner, member = company_with_team
        old_client, new_client = client_of(owner), client_of(member)
        assert transfer(old_client, member.pk).status_code == 200
        owner.refresh_from_db()
        member.refresh_from_db()
        assert (owner.role, member.role) == ("member", "owner")
        assert owners_of(company).count() == 1
        # the same tokens, new rights
        assert old_client.get(MEMBERS).status_code == 403
        assert new_client.get(MEMBERS).status_code == 200

    def test_it_needs_the_password(self, company_with_team):
        _, owner, member = company_with_team
        response = transfer(client_of(owner), member.pk, "not-my-password-1")
        assert (response.status_code, response.json()["error"]["code"]) == (400, "wrong_password")
        member.refresh_from_db()
        assert member.role == "member"

    def test_wrong_passwords_count_toward_the_login_pause(self, company_with_team):
        _, owner, member = company_with_team
        client = client_of(owner)
        codes = [transfer(client, member.pk, "wrong-password-12").status_code for _ in range(5)]
        assert codes == [400, 400, 400, 400, 429]
        assert transfer(client, member.pk).status_code == 429  # even the right one, while paused

    def test_a_missing_or_extra_field_is_refused(self, company_with_team):
        _, owner, member = company_with_team
        client = client_of(owner)
        assert client.post(TRANSFER, {"member_id": member.pk}, format="json").status_code == 400
        assert client.post(TRANSFER, {"password": PASSWORD}, format="json").status_code == 400
        body = {"member_id": member.pk, "password": PASSWORD, "role": "owner"}
        assert client.post(TRANSFER, body, format="json").status_code == 400

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_it_cannot_go_to_a_blocked_or_removed_person(self, company_with_team, status):
        company, owner, _ = company_with_team
        target = make_company_user(company, role="member", status=status)
        response = transfer(client_of(owner), target.pk)
        assert response.json()["error"]["code"] == "owner_transfer_refused"
        assert owners_of(company).get().pk == owner.pk

    def test_it_cannot_go_to_the_owner_themselves(self, company_with_team):
        company, owner, _ = company_with_team
        assert transfer(client_of(owner), owner.pk).status_code == 409
        assert owners_of(company).get().pk == owner.pk

    def test_it_cannot_go_to_someone_of_another_company(self, company_with_team):
        company, owner, _ = company_with_team
        _, other_owner = team(company=make_company(name="Fake Other Ltd"))
        assert transfer(client_of(owner), other_owner.pk).status_code == 404
        assert transfer(client_of(owner), 999999).status_code == 404
        other_owner.refresh_from_db()
        assert other_owner.role == "owner" and owners_of(company).get().pk == owner.pk

    def test_it_is_logged_in_the_audit_log_and_the_activity_log(self, company_with_team):
        company, owner, member = company_with_team
        transfer(client_of(owner), member.pk)
        audit = AuditEvent.objects.get(kind="team.ownership_transferred")
        assert (audit.actor_id, audit.target_id, audit.company_id) == (
            owner.pk,
            str(member.pk),
            company.pk,
        )
        entry = ActivityEntry.objects.get(kind="ownership_transferred")
        assert entry.details == {"new_owner_name": "Fake Member"}

    def test_a_failed_handover_logs_nothing(self, company_with_team):
        _, owner, member = company_with_team
        transfer(client_of(owner), member.pk, "wrong-password-12")
        assert not AuditEvent.objects.filter(kind="team.ownership_transferred").exists()
        assert not ActivityEntry.objects.filter(kind="ownership_transferred").exists()

    def test_a_member_cannot_hand_the_company_over(self, company_with_team):
        company, owner, member = company_with_team
        assert transfer(client_of(member), member.pk).status_code == 403
        assert owners_of(company).get().pk == owner.pk

    def test_the_former_owner_can_then_be_removed_by_the_new_owner(self, company_with_team):
        company, owner, member = company_with_team
        transfer(client_of(owner), member.pk)
        member.refresh_from_db()  # the test helper signs in as the role the object holds
        assert remove(client_of(member), owner).status_code == 204
        assert owners_of(company).get().pk == member.pk

    def test_there_is_always_exactly_one_owner(self, company_with_team):
        company, owner, member = company_with_team
        remove(client_of(owner), owner)  # refused
        transfer(client_of(owner), member.pk)
        member.refresh_from_db()  # the test helper signs in as the role the object holds
        remove(client_of(member), member)  # refused: now the owner
        assert owners_of(company).count() == 1
