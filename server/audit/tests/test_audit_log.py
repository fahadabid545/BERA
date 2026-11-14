import json

import pytest
from django.db import DatabaseError, connection, transaction
from rest_framework.test import APIClient

from adminusers.admin_accounts import change_role, set_status
from audit.events import KINDS
from audit.models import PERMANENT, AuditEvent
from audit.service import record
from companies.models import CompanyUser
from companies.tests.test_invites import GOOD, accept, client_of, invite, last_token, team
from core.errors import AppError, ConfigurationError
from core.tests.factories import make_admin_user
from twostep.tests.helpers import PASSWORD, person

pytestmark = pytest.mark.django_db
REASON = "Fake reason for the test."


def only():
    return AuditEvent.objects.get()


class TestWhatAnEntryHolds:
    def test_it_records_who_what_when_which_company_and_the_reason(self):
        company, owner = team()
        admin = make_admin_user()
        record(
            "admin.role_changed",
            actor=admin,
            target=owner,
            reason="  Asked by the owner.  ",
            details={"role_before": "owner", "role_after": "member"},
        )
        entry = only()
        assert entry.kind == "admin.role_changed" and entry.created_at is not None
        assert (entry.actor_kind, entry.actor_id) == ("admin", admin.pk)
        assert (entry.target_kind, entry.target_id) == ("company_user", str(owner.pk))
        assert entry.company_id == company.pk
        assert entry.reason == "Asked by the owner."
        assert entry.details == {"role_before": "owner", "role_after": "member"}

    def test_a_company_user_is_recorded_with_their_company(self):
        company, owner = team()
        record("invite.sent", actor=owner)
        assert (only().actor_kind, only().company_id) == ("company", company.pk)

    def test_an_action_with_nobody_signed_in_has_no_actor(self):
        record("auth.login_failed")
        assert (only().actor_kind, only().actor_id) == ("none", None)

    def test_an_unknown_kind_fails_loudly_instead_of_being_logged_under_an_invented_name(self):
        with pytest.raises(KeyError):
            record("something.invented")
        assert not AuditEvent.objects.exists()

    def test_entries_stay_after_the_account_is_gone(self):
        _, owner = team()
        record("invite.sent", actor=owner)
        CompanyUser.objects.filter(pk=owner.pk).delete()
        assert AuditEvent.objects.count() == 1


class TestTheWrittenReason:
    def test_the_actions_that_change_another_account_or_a_company_need_one(self):
        needing = {name for name, kind in KINDS.items() if kind.reason_required}
        assert needing == {
            "admin.candidate_data_exception",
            "admin.role_changed",
            "admin.status_changed",
            "admin.member_blocked",
            "admin.member_unblocked",
            "admin.plan_changed",
            "admin.plan_deleted",
            "admin.free_subscription_ended",
            "admin.free_subscription_granted",
            "admin.limit_changed",
            "admin.two_step_reset",
            "admin.company_two_step_off",
            "admin.company_suspended",
            "admin.company_unsuspended",
            "admin.subscription_terminated",
        }

    def test_logins_and_company_actions_need_none(self):
        for name in KINDS:
            if not name.startswith("admin."):
                assert not KINDS[name].reason_required

    @pytest.mark.parametrize("reason", ["", "   ", None])
    def test_without_a_reason_it_is_refused(self, reason):
        with pytest.raises(AppError) as error:
            record("admin.plan_changed", actor=make_admin_user(), reason=reason)
        assert error.value.code == "reason_required"
        assert not AuditEvent.objects.exists()

    def test_a_role_change_without_a_reason_is_undone(self):
        make_admin_user(role="super")
        admin = make_admin_user(role="super")
        with pytest.raises(AppError):
            change_role(admin.pk, "support", by=admin, reason=" ")
        admin.refresh_from_db()
        assert admin.role == "super" and not AuditEvent.objects.exists()

    def test_role_and_status_changes_are_recorded_with_old_and_new_values(self):
        boss = make_admin_user(role="super")
        other = make_admin_user(role="super")
        change_role(other.pk, "support", by=boss, reason=REASON)
        set_status(other.pk, "blocked", by=boss, reason=REASON)
        role, status = AuditEvent.objects.order_by("id")
        assert (role.kind, role.reason, role.actor_id, role.target_id) == (
            "admin.role_changed",
            REASON,
            boss.pk,
            str(other.pk),
        )
        assert role.details == {"role_before": "super", "role_after": "support"}
        assert status.kind == "admin.status_changed"
        assert status.details == {"status_before": "active", "status_after": "blocked"}

    def test_a_refused_change_leaves_no_entry(self):
        admin = make_admin_user(role="super")
        with pytest.raises(AppError):
            change_role(admin.pk, "support", by=admin, reason=REASON)  # the last super admin
        assert not AuditEvent.objects.exists()


class TestEntriesCannotBeChanged:
    def test_a_saved_entry_cannot_be_saved_again(self):
        record("auth.login")
        entry = only()
        entry.reason = "rewritten"
        with pytest.raises(ConfigurationError, match=PERMANENT):
            entry.save()

    def test_an_entry_cannot_be_deleted(self):
        record("auth.login")
        with pytest.raises(ConfigurationError):
            only().delete()

    def test_the_app_cannot_update_delete_or_bulk_update_entries(self):
        record("auth.login")
        with pytest.raises(ConfigurationError):
            AuditEvent.objects.update(reason="rewritten")
        with pytest.raises(ConfigurationError):
            AuditEvent.objects.all().delete()
        with pytest.raises(ConfigurationError):
            AuditEvent.objects.bulk_update([only()], ["reason"])
        assert AuditEvent.objects.count() == 1 and only().reason == ""

    def test_the_database_refuses_even_a_direct_change_or_removal(self):
        record("auth.login")
        for statement in (
            "UPDATE audit_auditevent SET reason = 'rewritten'",
            "DELETE FROM audit_auditevent",
        ):
            with pytest.raises(DatabaseError, match="permanent"):
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(statement)
        assert AuditEvent.objects.count() == 1 and only().reason == ""


class TestNothingSecretIsRecorded:
    @pytest.mark.parametrize(
        "name",
        ["password", "new_password", "token", "access_token", "secret", "code", "cv_text", "email"],
    )
    def test_details_with_a_name_that_suggests_a_secret_are_refused(self, name):
        with pytest.raises(ValueError):
            record("auth.login", details={name: "x"})

    def test_details_must_be_short_plain_values(self):
        with pytest.raises(ValueError):
            record("auth.login", details={"note": "x" * 500})
        with pytest.raises(ValueError):
            record("auth.login", details={"note": {"nested": 1}})

    def test_whole_flows_leave_no_password_token_code_or_address_in_the_log(self):
        company, owner = team()
        client = client_of(owner)
        invite(client)
        token = last_token()
        accept(token)
        account = person("someone@example.test")
        APIClient(REMOTE_ADDR="203.0.113.99").post(
            "/api/auth/company/login/",
            {"email": "typed-by-guesser@example.test", "password": "a-wrong-password-1"},
            format="json",
        )
        APIClient(REMOTE_ADDR="203.0.113.98").post(
            "/api/auth/company/login/",
            {"email": account.email, "password": "another-wrong-one-2"},
            format="json",
        )
        everything = json.dumps(list(AuditEvent.objects.values()), default=str)
        for secret in (
            token,
            GOOD,
            PASSWORD,
            "a-wrong-password-1",
            "another-wrong-one-2",
            "typed-by-guesser@example.test",
            "colleague@example.test",
            "someone@example.test",
        ):
            assert secret not in everything
        assert AuditEvent.objects.count() >= 4


class TestSignIns:
    def login(self, email, password, address="203.0.113.70"):
        return APIClient(REMOTE_ADDR=address).post(
            "/api/auth/company/login/", {"email": email, "password": password}, format="json"
        )

    def test_a_company_login_is_recorded(self):
        account = person()
        assert self.login(account.email, PASSWORD).status_code == 200
        entry = only()
        assert (entry.kind, entry.actor_kind, entry.actor_id) == (
            "auth.login",
            "company",
            account.pk,
        )
        assert entry.company_id == account.company_id

    def test_a_failed_login_names_the_account_tried_but_never_the_typed_address(self):
        account = person()
        assert self.login(account.email, "wrong-password-123").status_code == 400
        entry = only()
        assert (entry.kind, entry.actor_kind) == ("auth.login_failed", "none")
        assert (entry.target_kind, entry.target_id) == ("company_user", str(account.pk))

    def test_a_failed_login_for_an_address_with_no_account_is_recorded_too(self):
        self.login("nobody@example.test", "wrong-password-123")
        entry = only()
        assert (entry.kind, entry.target_kind, entry.target_id) == ("auth.login_failed", "", "")

    def test_a_right_password_alone_is_not_a_login_while_the_code_is_still_needed(self):
        account = person()
        from twostep.tests.helpers import turn_on

        turn_on(account)
        count = AuditEvent.objects.count()
        response = self.login(account.email, PASSWORD)
        assert response.json()["status"] == "two_step_required"
        assert AuditEvent.objects.count() == count  # no login entry yet

    def test_a_wrong_second_step_code_is_recorded(self):
        account = person()
        from twostep.tests.helpers import turn_on

        turn_on(account)
        challenge = self.login(account.email, PASSWORD).json()["challenge"]
        APIClient(REMOTE_ADDR="203.0.113.70").post(
            "/api/auth/company/login/two-step/",
            {"challenge": challenge, "code": "000000"},
            format="json",
        )
        entry = AuditEvent.objects.get(kind="auth.two_step_failed")
        assert (entry.target_kind, entry.target_id) == ("company_user", str(account.pk))

    def test_admin_logins_are_recorded_as_admin_entries(self):
        from adminusers.tests.test_admin_login import VERIFY, enrolled, password_step, post

        account, secret = enrolled()
        entries = list(AuditEvent.objects.order_by("id"))
        assert [e.kind for e in entries] == ["auth.login"]  # the setup finished a login
        assert (entries[0].actor_kind, entries[0].actor_id) == ("admin", account.pk)
        password_step("nobody@example.test", "wrong-password-123")
        challenge = password_step(account.email).json()["challenge"]
        post(VERIFY, {"challenge": challenge, "code": "000000"})
        kinds = [e.kind for e in AuditEvent.objects.order_by("id")]
        assert kinds == ["auth.login", "auth.login_failed", "auth.two_step_failed"]
        assert AuditEvent.objects.get(kind="auth.two_step_failed").target_kind == "admin_user"


class TestInvitations:
    def test_sending_resending_revoking_and_accepting_are_recorded(self):
        company, owner = team()
        client = client_of(owner)
        invitation_id = invite(client).json()["id"]
        client.post(f"/api/company/team/invites/{invitation_id}/resend/")
        accept(last_token())
        other = invite(client, "second@example.test").json()["id"]
        client.delete(f"/api/company/team/invites/{other}/")
        kinds = list(AuditEvent.objects.order_by("id").values_list("kind", flat=True))
        assert kinds == [
            "invite.sent",
            "invite.resent",
            "invite.accepted",
            "invite.sent",
            "invite.revoked",
        ]
        sent = AuditEvent.objects.filter(kind="invite.sent").first()
        assert (sent.actor_kind, sent.actor_id, sent.company_id) == (
            "company",
            owner.pk,
            company.pk,
        )
        assert (sent.target_kind, sent.target_id) == ("invitation", invitation_id)
        accepted = AuditEvent.objects.get(kind="invite.accepted")
        member = CompanyUser.objects.get(email="colleague@example.test")
        assert (accepted.actor_kind, accepted.actor_id) == ("company", member.pk)

    def test_a_refused_invitation_leaves_no_entry(self):
        company, owner = team()
        client = client_of(owner)
        invite(client)
        before = AuditEvent.objects.count()
        assert invite(client).status_code == 409  # already invited
        assert AuditEvent.objects.count() == before


def test_the_first_super_admin_is_recorded():
    from adminusers.first_super_admin import create_first_super_admin

    admin = create_first_super_admin(name="Fake Boss", email="boss@example.test", password=PASSWORD)
    entry = only()
    assert (entry.kind, entry.actor_kind, entry.target_id) == (
        "admin.first_super_admin_created",
        "none",
        str(admin.pk),
    )
