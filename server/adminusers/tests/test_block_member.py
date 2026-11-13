import pytest
from rest_framework.test import APIClient

from audit.models import AuditEvent
from companies.models import CompanyUser
from companies.tests.test_invites import client_of, team
from core.tests.factories import make_admin_user, make_company, make_company_user
from emailing.models import OutgoingEmail
from signin import service as signin
from signin.models import Session

pytestmark = pytest.mark.django_db
REASON = "Fake reason for the test."
PASSWORD = "Correct-Horse-9-Battery"
BLOCKED_MESSAGE = "Your access has been blocked. Please contact your company owner or support."


def admin_client(role):
    admin = make_admin_user(role=role)
    issued = signin.start_session(user_id=admin.pk, role=role, company_id=None, kind="admin")
    return admin, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def url(person, action):
    return f"/api/admin/company-users/{person.pk}/{action}/"


def act(client, person, action, **body):
    return client.post(url(person, action), body, format="json")


def sessions_of(person):
    return Session.objects.filter(user_id=person.pk, kind="company", status="active").count()


def log_in(person, password=PASSWORD):
    return APIClient().post(
        "/api/auth/company/login/", {"email": person.email, "password": password}, format="json"
    )


@pytest.fixture
def members():
    company, owner = team()
    member = make_company_user(company, role="member", email_verified=True)
    member.set_password(PASSWORD)
    member.save()
    return company, owner, member


@pytest.mark.parametrize("role", ["super", "support"])
class TestBlocking:
    def test_it_blocks_signs_the_person_out_at_once_and_audits(self, members, role):
        admin, client = admin_client(role)
        _, _, member = members
        issued = signin.start_session(
            user_id=member.pk, role="member", company_id=member.company_id, kind="company"
        )
        signin.start_session(
            user_id=member.pk, role="member", company_id=member.company_id, kind="company"
        )
        assert sessions_of(member) == 2
        response = act(client, member, "block", reason=REASON)
        assert response.status_code == 200 and response.json() == {"status": "blocked"}
        member.refresh_from_db()
        assert member.status == CompanyUser.Status.BLOCKED
        assert sessions_of(member) == 0
        old = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert old.get("/api/company/usage/").status_code == 401
        event = AuditEvent.objects.get(kind="admin.member_blocked")
        assert (event.actor_id, event.target_id, event.reason) == (
            admin.pk,
            str(member.pk),
            REASON,
        )
        assert event.company_id == member.company_id

    def test_the_owner_is_emailed(self, members, role):
        _, client = admin_client(role)
        company, owner, member = members
        act(client, member, "block", reason=REASON)
        mails = [e for e in OutgoingEmail.objects.all() if e.to_address == owner.email]
        assert len(mails) == 1 and mails[0].template == "account_notice"
        assert member.name in mails[0].text_body

    def test_unblocking_restores_access_and_emails_the_owner(self, members, role):
        admin, client = admin_client(role)
        company, owner, member = members
        act(client, member, "block", reason=REASON)
        response = act(client, member, "unblock", reason="Fake second reason.")
        assert response.status_code == 200 and response.json() == {"status": "active"}
        member.refresh_from_db()
        assert member.status == CompanyUser.Status.ACTIVE
        assert log_in(member).status_code == 200
        assert AuditEvent.objects.get(kind="admin.member_unblocked").reason == "Fake second reason."
        assert len([e for e in OutgoingEmail.objects.all() if e.to_address == owner.email]) == 2

    def test_old_sessions_do_not_come_back_after_unblocking(self, members, role):
        _, client = admin_client(role)
        _, _, member = members
        issued = signin.start_session(
            user_id=member.pk, role="member", company_id=member.company_id, kind="company"
        )
        act(client, member, "block", reason=REASON)
        act(client, member, "unblock", reason=REASON)
        old = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert old.get("/api/company/team/members/").status_code == 401

    def test_the_owner_cannot_be_blocked(self, members, role):
        _, client = admin_client(role)
        _, owner, _ = members
        response = act(client, owner, "block", reason=REASON)
        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "owner_cannot_be_blocked",
        )
        owner.refresh_from_db()
        assert owner.status == CompanyUser.Status.ACTIVE
        assert not AuditEvent.objects.filter(kind="admin.member_blocked").exists()

    @pytest.mark.parametrize("reason", [None, "", "   "])
    def test_a_reason_is_required_for_both_actions(self, members, role, reason):
        _, client = admin_client(role)
        _, _, member = members
        body = {} if reason is None else {"reason": reason}
        assert act(client, member, "block", **body).status_code == 400
        member.status = "blocked"
        member.save()
        assert act(client, member, "unblock", **body).status_code == 400
        member.refresh_from_db()
        assert member.status == "blocked"
        assert not AuditEvent.objects.filter(kind__startswith="admin.member").exists()

    def test_blocking_twice_or_unblocking_an_active_person_is_refused(self, members, role):
        _, client = admin_client(role)
        _, _, member = members
        assert act(client, member, "unblock", reason=REASON).status_code == 409
        act(client, member, "block", reason=REASON)
        again = act(client, member, "block", reason=REASON)
        assert (again.status_code, again.json()["error"]["code"]) == (409, "already_blocked")
        assert AuditEvent.objects.filter(kind="admin.member_blocked").count() == 1

    def test_a_removed_person_cannot_be_blocked_or_brought_back(self, members, role):
        _, client = admin_client(role)
        _, _, member = members
        CompanyUser.objects.filter(pk=member.pk).update(status="removed")
        assert act(client, member, "block", reason=REASON).status_code == 409
        assert act(client, member, "unblock", reason=REASON).status_code == 409

    def test_an_unknown_person_is_not_found(self, role):
        _, client = admin_client(role)
        response = client.post(
            "/api/admin/company-users/999999/block/", {"reason": REASON}, format="json"
        )
        assert response.status_code == 404

    def test_only_that_person_is_affected(self, members, role):
        _, client = admin_client(role)
        company, owner, member = members
        other = make_company_user(company, role="member")
        signin.start_session(user_id=other.pk, role="member", company_id=company.pk, kind="company")
        act(client, member, "block", reason=REASON)
        other.refresh_from_db()
        assert other.status == "active" and sessions_of(other) == 1


class TestWhatTheBlockedPersonSees:
    def test_the_right_password_shows_the_blocked_message(self, members):
        _, client = admin_client("support")
        _, _, member = members
        act(client, member, "block", reason=REASON)
        response = log_in(member)
        assert (response.status_code, response.json()["error"]["code"]) == (403, "access_blocked")
        assert response.json()["error"]["message"] == BLOCKED_MESSAGE
        assert sessions_of(member) == 0

    def test_a_wrong_password_still_gets_the_neutral_failure(self, members):
        _, client = admin_client("support")
        _, _, member = members
        act(client, member, "block", reason=REASON)
        response = log_in(member, "Wrong-Password-9-Nope")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_every_request_with_an_old_session_answers_the_same_401(self, members):
        _, client = admin_client("super")
        _, _, member = members
        issued = signin.start_session(
            user_id=member.pk, role="member", company_id=member.company_id, kind="company"
        )
        act(client, member, "block", reason=REASON)
        blocked = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}").get(
            "/api/company/usage/"
        )
        nobody = APIClient().get("/api/company/usage/")
        assert blocked.status_code == nobody.status_code == 401
        assert blocked.json() == nobody.json()


class TestWhoMayDoIt:
    def test_visitors_and_company_sign_ins_are_refused(self, members):
        _, owner, member = members
        assert APIClient().post(url(member, "block"), {}, format="json").status_code == 401
        response = client_of(owner).post(url(member, "block"), {"reason": REASON}, format="json")
        assert response.status_code == 401
        member.refresh_from_db()
        assert member.status == "active"

    def test_a_blocked_admin_cannot_block_anyone(self, members):
        admin, client = admin_client("super")
        admin.status = "blocked"
        admin.save()
        _, _, member = members
        assert act(client, member, "block", reason=REASON).status_code == 401

    def test_members_of_other_companies_are_reachable_by_admins_only(self, members):
        other = make_company_user(make_company(), role="member")
        _, client = admin_client("support")
        assert act(client, other, "block", reason=REASON).status_code == 200
