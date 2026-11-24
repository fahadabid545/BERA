"""Managing admins: invite, accept, resend, revoke, change role, disable and enable. Super admin
only, and every action is audited."""

import re
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers.models import AdminInvitation, AdminUser
from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from core.tests.factories import make_admin_user
from cvs.tests.test_ai_reading import set_setting
from emailing.models import LinkToken, OutgoingEmail

pytestmark = pytest.mark.django_db
TEAM = "/api/admin/admin-users/"
INVITE = TEAM + "invitations/"
ACCEPT = "/api/auth/admin/accept-invite/"
LOGIN = "/api/auth/admin/login/"
GOOD = "copper-meadow-lantern-58"  # nosecret: fake test value
EMAIL = "new-admin@example.test"


@pytest.fixture
def boss():
    return admin_client("super")


def invite(client, email=EMAIL, role="support", **over):
    body = {
        "name": "Fake New Admin",
        "email": email,
        "role": role,
        "reason": "Fake reason.",
        **over,
    }
    return client.post(INVITE, body, format="json")


def last_token(email=EMAIL):
    for sent in OutgoingEmail.objects.filter(template="admin_invite").order_by("-created_at"):
        if sent.to_address == email:
            return re.search(r"/admin/accept-invite\?token=([\w-]+)", sent.text_body).group(1)
    raise AssertionError("no invitation email was sent")


def accept(token, password=GOOD, confirm=None):
    body = {
        "token": token,
        "password": password,
        "confirm_password": password if confirm is None else confirm,
    }
    return APIClient(REMOTE_ADDR="203.0.113.70").post(ACCEPT, body, format="json")


def audit(kind):
    return AuditEvent.objects.filter(kind=kind)


class TestInviting:
    def test_an_invitation_is_sent_by_email_and_listed(self, boss):
        client, me = boss
        reply = invite(client, role="super")
        assert reply.status_code == 201
        [waiting] = reply.json()["invitations"]
        assert (waiting["name"], waiting["email"], waiting["role"], waiting["status"]) == (
            "Fake New Admin",
            EMAIL,
            "super",
            "pending",
        )
        assert OutgoingEmail.objects.filter(template="admin_invite").count() == 1

    def test_the_email_holds_the_link_and_no_password(self, boss):
        invite(boss[0])
        mail = OutgoingEmail.objects.get(template="admin_invite")
        assert "/admin/accept-invite?token=" in mail.text_body
        assert "password" not in mail.text_body.lower().replace("choose your password", "")

    def test_the_audit_log_has_who_and_the_reason_but_not_the_address(self, boss):
        client, me = boss
        invite(client)
        event = audit("admin.invited").get()
        assert (event.actor_id, event.reason) == (me.pk, "Fake reason.")
        assert EMAIL not in str(event.details)

    def test_a_reason_is_required(self, boss):
        reply = boss[0].post(
            INVITE,
            {"name": "Fake New Admin", "email": EMAIL, "role": "support"},
            format="json",
        )
        assert reply.status_code == 400
        assert "reason" in reply.json()["error"]["fields"]
        assert AdminInvitation.objects.count() == 0

    @pytest.mark.parametrize(
        "over, field",
        [
            ({"email": "not an address"}, "email"),
            ({"name": ""}, "name"),
            ({"role": "owner"}, "role"),
            ({"reason": ""}, "reason"),
        ],
    )
    def test_a_bad_form_is_refused(self, boss, over, field):
        reply = invite(boss[0], **over)
        assert reply.status_code == 400
        assert field in reply.json()["error"]["fields"]

    def test_an_address_that_is_already_an_active_admin_is_refused(self, boss):
        make_admin_user(email=EMAIL)
        reply = invite(boss[0])
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "account_exists")
        assert AdminInvitation.objects.count() == 0

    def test_a_disabled_admin_address_is_refused_too(self, boss):
        make_admin_user(email=EMAIL, status="blocked")
        assert invite(boss[0]).status_code == 409

    def test_the_address_is_matched_in_any_letter_case(self, boss):
        make_admin_user(email=EMAIL)
        assert invite(boss[0], email="  New-Admin@Example.test ").status_code == 409

    def test_an_address_with_a_pending_invitation_is_refused(self, boss):
        invite(boss[0])
        reply = invite(boss[0])
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "already_invited")

    def test_support_is_refused_and_nothing_is_sent(self):
        support = admin_client("support")[0]
        assert invite(support).status_code == 403
        assert support.get(TEAM).status_code == 403
        assert not OutgoingEmail.objects.exists() and not AdminInvitation.objects.exists()

    def test_a_company_person_and_a_visitor_are_refused(self, client):
        assert invite(client).status_code == 401


class TestAccepting:
    def test_the_invitee_sets_a_password_and_becomes_the_invited_role(self, boss):
        invite(boss[0], role="super")
        assert accept(last_token()).status_code == 200
        created = AdminUser.objects.get(email=EMAIL)
        assert (created.name, created.role, created.status) == ("Fake New Admin", "super", "active")
        assert created.check_password(GOOD)
        assert AdminInvitation.objects.get().status == "accepted"
        assert audit("admin.invite_accepted").get().actor_id == created.pk

    def test_two_step_setup_is_asked_at_the_first_sign_in(self, boss):
        invite(boss[0])
        accept(last_token())
        reply = APIClient(REMOTE_ADDR="203.0.113.71").post(
            LOGIN, {"email": EMAIL, "password": GOOD}, format="json"
        )
        assert reply.json()["status"] == "two_step_setup_required"

    def test_the_link_works_once(self, boss):
        invite(boss[0])
        token = last_token()
        assert accept(token).status_code == 200
        again = accept(token)
        assert (again.status_code, again.json()["error"]["code"]) == (400, "link_used")
        assert AdminUser.objects.filter(email=EMAIL).count() == 1

    def test_a_weak_password_is_refused_and_the_link_still_works(self, boss):
        invite(boss[0])
        token = last_token()
        assert accept(token, password="short").status_code == 400
        assert accept(token, confirm="another-different-pass-77").status_code == 400
        assert accept(token).status_code == 200

    def test_an_expired_link_is_refused(self, boss):
        invite(boss[0])
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        assert accept(last_token()).json()["error"]["code"] == "link_expired"

    def test_the_lifetime_is_a_platform_setting(self, boss):
        set_setting("tokens.admin_invite_days", 2)
        invite(boss[0])
        token = LinkToken.objects.get(purpose="admin_invite")
        assert timedelta(days=1, hours=23) < token.expires_at - timezone.now() <= timedelta(days=2)

    def test_a_link_for_something_else_does_not_work(self, boss):
        from emailing.link_tokens import issue_link_token

        invite(boss[0])
        other = issue_link_token("team_invite", AdminInvitation.objects.get().token_subject, 1)
        assert accept(other).status_code == 400

    def test_an_invitation_whose_address_became_an_admin_meanwhile_is_refused(self, boss):
        invite(boss[0])
        make_admin_user(email=EMAIL)
        assert accept(last_token()).json()["error"]["code"] == "account_exists"


class TestResendAndRevoke:
    def test_a_resend_sends_a_new_link_and_the_old_one_stops_working(self, boss):
        client, _ = boss
        invite(client)
        first = last_token()
        waiting = client.get(TEAM).json()["invitations"][0]
        assert client.post(f"{INVITE}{waiting['id']}/resend/").status_code == 200
        assert OutgoingEmail.objects.filter(template="admin_invite").count() == 2
        assert accept(first).status_code == 400
        assert accept(last_token()).status_code == 200
        assert audit("admin.invite_resent").count() == 1

    def test_an_expired_invitation_is_listed_as_expired_and_can_be_resent(self, boss):
        client, _ = boss
        invite(client)
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        waiting = client.get(TEAM).json()["invitations"][0]
        assert waiting["status"] == "expired"
        client.post(f"{INVITE}{waiting['id']}/resend/")
        assert client.get(TEAM).json()["invitations"][0]["status"] == "pending"

    def test_a_revoked_invitation_cannot_be_accepted_and_can_be_made_again(self, boss):
        client, _ = boss
        invite(client)
        token = last_token()
        waiting = client.get(TEAM).json()["invitations"][0]
        reply = client.post(f"{INVITE}{waiting['id']}/revoke/")
        assert reply.status_code == 200 and reply.json()["invitations"] == []
        assert accept(token).status_code == 400
        assert not AdminUser.objects.filter(email=EMAIL).exists()
        assert audit("admin.invite_revoked").count() == 1
        assert invite(client).status_code == 201

    def test_a_closed_invitation_cannot_be_resent_or_revoked(self, boss):
        client, _ = boss
        invite(client)
        accept(last_token())
        done = AdminInvitation.objects.get()
        for action in ("resend", "revoke"):
            reply = client.post(f"{INVITE}{done.pk}/{action}/")
            assert (reply.status_code, reply.json()["error"]["code"]) == (409, "invitation_closed")

    def test_an_unknown_invitation_is_not_found(self, boss):
        for action in ("resend", "revoke"):
            assert boss[0].post(f"{INVITE}999999/{action}/").status_code == 404

    def test_support_is_refused(self, boss):
        invite(boss[0])
        waiting = AdminInvitation.objects.get()
        support = admin_client("support")[0]
        for action in ("resend", "revoke"):
            assert support.post(f"{INVITE}{waiting.pk}/{action}/").status_code == 403
        assert AdminInvitation.objects.get().status == "pending"


class TestRoleAndStatus:
    def test_the_list_shows_admins_with_their_two_step_state(self, boss):
        other = make_admin_user(role="support", two_step_enabled=True)
        admins = {a["id"]: a for a in boss[0].get(TEAM).json()["admins"]}
        assert (admins[other.pk]["role"], admins[other.pk]["two_step_enabled"]) == ("support", True)
        assert "password" not in str(admins)

    def test_the_role_changes_with_a_reason_and_is_audited(self, boss):
        other = make_admin_user(role="support")
        reply = boss[0].post(
            f"{TEAM}{other.pk}/role/", {"role": "super", "reason": "Fake reason."}, format="json"
        )
        assert reply.status_code == 200
        other.refresh_from_db()
        assert other.role == "super"
        assert audit("admin.role_changed").get().reason == "Fake reason."

    def test_a_role_change_without_a_reason_is_refused(self, boss):
        other = make_admin_user(role="support")
        reply = boss[0].post(f"{TEAM}{other.pk}/role/", {"role": "super"}, format="json")
        assert reply.status_code == 400
        other.refresh_from_db()
        assert other.role == "support"

    def test_disabling_and_enabling_are_audited(self, boss):
        other = make_admin_user()
        for status in ("blocked", "active"):
            reply = boss[0].post(
                f"{TEAM}{other.pk}/status/", {"status": status, "reason": "Fake."}, format="json"
            )
            assert reply.status_code == 200
        assert audit("admin.status_changed").count() == 2
        other.refresh_from_db()
        assert other.status == "active"

    def test_a_disabled_admin_is_signed_out_at_once(self, boss):
        victim, me = admin_client("support")
        assert victim.get(TEAM + "../dashboard/").status_code in (200, 403, 404)
        boss[0].post(
            f"{TEAM}{me.pk}/status/", {"status": "blocked", "reason": "Fake."}, format="json"
        )
        assert victim.get("/api/admin/data-requests/").status_code == 401

    def test_the_last_super_admin_cannot_be_disabled_or_demoted(self, boss):
        client, me = boss
        for path, body in (
            ("status", {"status": "blocked", "reason": "Fake."}),
            ("role", {"role": "support", "reason": "Fake."}),
        ):
            reply = client.post(f"{TEAM}{me.pk}/{path}/", body, format="json")
            assert (reply.status_code, reply.json()["error"]["code"]) == (409, "last_super_admin")
        me.refresh_from_db()
        assert (me.role, me.status) == ("super", "active")

    def test_a_super_admin_can_be_disabled_while_another_is_active(self, boss):
        client, me = boss
        other = make_admin_user(role="super")
        reply = client.post(
            f"{TEAM}{other.pk}/status/", {"status": "blocked", "reason": "Fake."}, format="json"
        )
        assert reply.status_code == 200

    def test_a_pending_invitation_does_not_count_as_another_super_admin(self, boss):
        client, me = boss
        invite(client, role="super")
        reply = client.post(
            f"{TEAM}{me.pk}/status/", {"status": "blocked", "reason": "Fake."}, format="json"
        )
        assert reply.status_code == 409

    def test_two_step_is_never_a_per_admin_switch(self, boss):
        other = make_admin_user()
        reply = boss[0].post(
            f"{TEAM}{other.pk}/status/",
            {"status": "active", "reason": "Fake.", "two_step_required": False},
            format="json",
        )
        assert reply.status_code == 400

    @pytest.mark.parametrize("path", ["role", "status"])
    def test_support_is_refused(self, path):
        support = admin_client("support")[0]
        other = make_admin_user(role="support")
        body = {"role": "super"} if path == "role" else {"status": "blocked"}
        reply = support.post(
            f"{TEAM}{other.pk}/{path}/", {**body, "reason": "Fake."}, format="json"
        )
        assert reply.status_code == 403
        other.refresh_from_db()
        assert (other.role, other.status) == ("support", "active")

    def test_an_unknown_admin_is_not_found(self, boss):
        reply = boss[0].post(
            f"{TEAM}999999/status/", {"status": "blocked", "reason": "Fake."}, format="json"
        )
        assert reply.status_code == 404

    def test_a_status_other_than_active_or_blocked_is_refused(self, boss):
        other = make_admin_user()
        reply = boss[0].post(
            f"{TEAM}{other.pk}/status/", {"status": "removed", "reason": "Fake."}, format="json"
        )
        assert reply.status_code == 400


def test_a_company_person_cannot_reach_the_team_routes(client):

    assert client.get(TEAM).status_code == 401


def test_accepting_with_a_made_up_link_creates_no_account():
    reply = accept("made-up-secret")
    assert (reply.status_code, reply.json()["error"]["code"]) == (400, "link_invalid")
    assert not AdminUser.objects.exists()
