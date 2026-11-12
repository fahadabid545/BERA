import re
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from companies.models import Company, CompanyUser, Invitation
from core.tests.factories import make_company, make_company_user, start_session_for
from emailing import link_tokens
from emailing.models import LinkToken, OutgoingEmail
from platform_settings import service as platform_settings
from platform_settings.models import PlatformSetting

INVITES = "/api/company/team/invites/"
ACCEPT = "/api/auth/company/accept-invite/"
GOOD = "copper-meadow-lantern-58"  # nosecret: fake test value
pytestmark = pytest.mark.django_db


def setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    platform_settings.clear_cache()


def team(role="owner", company=None, suffix=""):
    company = company or make_company(name="Fake Team Ltd")
    person = make_company_user(company, role=role, name=f"Fake {role.title()}", email_verified=True)
    return company, person


def client_of(person, address="203.0.113.50"):
    issued = start_session_for(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind="company"
    )
    return APIClient(REMOTE_ADDR=address, HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def invite(client, email="colleague@example.test"):
    return client.post(INVITES, {"email": email}, format="json")


def last_token(email="colleague@example.test"):
    mail = OutgoingEmail.objects.filter(template="team_invite").order_by("-created_at")
    for sent in mail:
        if sent.to_address == email:
            return re.search(r"/accept-invite\?token=([\w-]+)", sent.text_body).group(1)
    raise AssertionError("no invitation email was sent")


def accept(token, name="Fake Invitee", password=GOOD, confirm=None, address="203.0.113.60"):
    body = {
        "token": token,
        "name": name,
        "password": password,
        "confirm_password": password if confirm is None else confirm,
    }
    return APIClient(REMOTE_ADDR=address).post(ACCEPT, body, format="json")


def code(response):
    return response.json()["error"]["code"]


class TestInviting:
    def test_the_invitee_gets_an_email_with_a_link_valid_for_seven_days(self):
        company, owner = team()
        response = invite(client_of(owner))
        assert response.status_code == 201
        sent = OutgoingEmail.objects.get(template="team_invite")
        assert sent.to_address == "colleague@example.test"
        assert "Fake Owner" in sent.text_body and "Fake Team Ltd" in sent.text_body
        assert "7 days" in sent.text_body and "/accept-invite?token=" in sent.text_body
        stored = LinkToken.objects.get(purpose="team_invite")
        assert timedelta(days=6, hours=23) < stored.expires_at - timezone.now() <= timedelta(days=7)

    def test_the_lifetime_follows_the_platform_setting(self):
        setting("tokens.team_invite_days", 3)
        _, owner = team()
        invite(client_of(owner))
        stored = LinkToken.objects.get(purpose="team_invite")
        assert stored.expires_at - timezone.now() <= timedelta(days=3)
        assert "3 days" in OutgoingEmail.objects.get(template="team_invite").text_body

    def test_the_token_is_stored_only_as_a_hash_and_the_email_only_encrypted(self):
        _, owner = team()
        invite(client_of(owner))
        token = last_token()
        with connection.cursor() as cursor:
            cursor.execute("select token_hash from emailing_linktoken")
            hashes = [row[0] for row in cursor.fetchall()]
            cursor.execute("select email, email_lookup from companies_invitation")
            email_columns = cursor.fetchone()
        assert token not in hashes and len(hashes[0]) == 64
        assert "colleague@example.test" not in "".join(email_columns)

    def test_tokens_are_random_and_not_repeated(self):
        _, owner = team()
        setting("team.max_accounts_per_company", 50)
        client = client_of(owner)
        invite(client, "a@example.test")
        invite(client, "b@example.test")
        assert last_token("a@example.test") != last_token("b@example.test")

    def test_the_address_must_be_an_email(self):
        _, owner = team()
        response = invite(client_of(owner), "not-an-email")
        assert response.status_code == 400 and "email" in response.json()["error"]["fields"]
        assert not Invitation.objects.exists()

    def test_extra_fields_are_refused(self):
        _, owner = team()
        response = client_of(owner).post(
            INVITES, {"email": "a@example.test", "role": "owner"}, format="json"
        )
        assert response.status_code == 400

    def test_the_new_member_is_never_an_owner(self):
        _, owner = team()
        invite(client_of(owner))
        accept(last_token())
        assert CompanyUser.objects.get(email="colleague@example.test").role == "member"


class TestAddressesThatAlreadyHaveAnAccount:
    @pytest.mark.parametrize("status", ["active", "blocked", "removed"])
    def test_an_address_with_an_account_gets_a_clear_message(self, status):
        _, owner = team()
        make_company_user(email="colleague@example.test", status=status)
        response = invite(client_of(owner))
        assert (response.status_code, code(response)) == (409, "account_exists")
        assert response.json()["error"]["message"] == "This email already has an account."
        assert not Invitation.objects.exists()

    def test_it_makes_no_difference_which_company_has_the_account_or_how_it_is_typed(self):
        _, owner = team()
        make_company_user(make_company(), email="colleague@example.test")
        response = invite(client_of(owner), "  Colleague@Example.TEST ")
        assert code(response) == "account_exists"

    def test_a_pending_invitation_cannot_be_repeated(self):
        _, owner = team()
        client = client_of(owner)
        invite(client)
        response = invite(client)
        assert (response.status_code, code(response)) == (409, "already_invited")
        assert Invitation.objects.count() == 1

    def test_after_a_revoke_the_address_can_be_invited_again(self):
        _, owner = team()
        client = client_of(owner)
        first = invite(client).json()["id"]
        client.delete(f"{INVITES}{first}/")
        assert invite(client).status_code == 201


class TestTheLimit:
    def test_three_accounts_including_the_owner(self):
        _, owner = team()
        client = client_of(owner)
        assert invite(client, "a@example.test").status_code == 201
        assert invite(client, "b@example.test").status_code == 201
        response = invite(client, "c@example.test")
        assert (response.status_code, code(response)) == (409, "team_limit_reached")
        assert "at most 3 accounts" in response.json()["error"]["message"]
        assert response.json()["error"]["details"] == {"limit": 3}

    def test_the_limit_is_the_platform_setting(self):
        setting("team.max_accounts_per_company", 2)
        _, owner = team()
        client = client_of(owner)
        assert invite(client, "a@example.test").status_code == 201
        response = invite(client, "b@example.test")
        assert "at most 2 accounts" in response.json()["error"]["message"]

    def test_members_count_and_removed_people_do_not(self):
        company, owner = team()
        make_company_user(company, role="member")
        removed = make_company_user(company, role="member", status="removed")
        client = client_of(owner)
        assert invite(client, "a@example.test").status_code == 201  # owner + member + invitee
        assert code(invite(client, "b@example.test")) == "team_limit_reached"
        assert removed.status == "removed"

    def test_revoking_or_an_expired_link_frees_the_seat(self):
        _, owner = team()
        setting("team.max_accounts_per_company", 2)
        client = client_of(owner)
        first = invite(client, "a@example.test").json()["id"]
        client.delete(f"{INVITES}{first}/")
        second = invite(client, "b@example.test")
        assert second.status_code == 201
        LinkToken.objects.filter(purpose="team_invite", used_at__isnull=True).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert invite(client, "c@example.test").status_code == 201

    def test_another_company_has_its_own_seats(self):
        _, owner = team()
        _, other_owner = team()
        for email in ("a@example.test", "b@example.test"):
            invite(client_of(owner), email)
        assert invite(client_of(other_owner), "c@example.test").status_code == 201

    def test_the_limit_is_checked_again_when_the_invitation_is_accepted(self):
        _, owner = team()
        invite(client_of(owner))
        token = last_token()
        setting("team.max_accounts_per_company", 1)
        response = accept(token)
        assert code(response) == "team_limit_reached"
        assert not CompanyUser.objects.filter(email="colleague@example.test").exists()


class TestTheInviteRateLimit:
    def test_twenty_an_hour_for_each_company(self):
        setting("team.max_accounts_per_company", 100)
        _, owner = team()
        client = client_of(owner)
        statuses = [invite(client, f"person{n}@example.test").status_code for n in range(21)]
        assert statuses == [201] * 20 + [429]

    def test_another_company_is_not_slowed_down(self):
        setting("team.max_accounts_per_company", 100)
        _, owner = team()
        _, other = team()
        for n in range(21):
            invite(client_of(owner), f"person{n}@example.test")
        assert invite(client_of(other), "fresh@example.test").status_code == 201

    def test_resending_counts_too(self):
        setting("team.max_accounts_per_company", 100)
        setting("rate_limits.invites_per_hour", 3)
        _, owner = team()
        client = client_of(owner)
        first = invite(client, "a@example.test").json()["id"]
        statuses = [client.post(f"{INVITES}{first}/resend/").status_code for _ in range(3)]
        assert statuses == [200, 200, 429]

    def test_the_limit_is_the_platform_setting(self):
        setting("team.max_accounts_per_company", 100)
        setting("rate_limits.invites_per_hour", 2)
        _, owner = team()
        client = client_of(owner)
        statuses = [invite(client, f"p{n}@example.test").status_code for n in range(3)]
        assert statuses == [201, 201, 429]


class TestThePendingList:
    def test_it_shows_pending_and_expired_invitations_but_not_closed_ones(self):
        _, owner = team()
        setting("team.max_accounts_per_company", 50)
        client = client_of(owner)
        invite(client, "open@example.test")
        invite(client, "old@example.test")
        revoked = invite(client, "gone@example.test").json()["id"]
        client.delete(f"{INVITES}{revoked}/")
        invite(client, "joined@example.test")
        accept(last_token("joined@example.test"))
        old = Invitation.objects.get(email_lookup="old@example.test")
        LinkToken.objects.filter(subject_id=old.token_subject).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        listed = {item["email"]: item["status"] for item in client.get(INVITES).json()}
        assert listed == {"open@example.test": "pending", "old@example.test": "expired"}

    def test_it_shows_only_the_own_company(self):
        _, owner = team()
        _, other_owner = team()
        invite(client_of(other_owner), "theirs@example.test")
        invite(client_of(owner), "mine@example.test")
        assert [i["email"] for i in client_of(owner).get(INVITES).json()] == ["mine@example.test"]


class TestResending:
    def test_a_new_link_replaces_the_old_one(self):
        _, owner = team()
        client = client_of(owner)
        identifier = invite(client).json()["id"]
        old = last_token()
        assert client.post(f"{INVITES}{identifier}/resend/").status_code == 200
        new = last_token()
        assert new != old
        assert OutgoingEmail.objects.filter(template="team_invite").count() == 2
        assert code(accept(old)) == "link_used"
        assert accept(new).status_code == 200

    def test_an_expired_invitation_can_be_sent_again(self):
        _, owner = team()
        client = client_of(owner)
        identifier = invite(client).json()["id"]
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        assert code(accept(last_token())) == "link_expired"
        assert client.post(f"{INVITES}{identifier}/resend/").status_code == 200
        assert accept(last_token()).status_code == 200

    @pytest.mark.parametrize("how", ["revoked", "accepted"])
    def test_a_closed_invitation_cannot_be_resent(self, how):
        _, owner = team()
        client = client_of(owner)
        identifier = invite(client).json()["id"]
        if how == "revoked":
            client.delete(f"{INVITES}{identifier}/")
        else:
            accept(last_token())
        response = client.post(f"{INVITES}{identifier}/resend/")
        assert (response.status_code, code(response)) == (409, "invitation_closed")


class TestRevoking:
    def test_a_revoked_link_stops_working_with_a_clear_message(self):
        _, owner = team()
        client = client_of(owner)
        identifier = invite(client).json()["id"]
        token = last_token()
        assert client.delete(f"{INVITES}{identifier}/").status_code == 204
        response = accept(token)
        assert (response.status_code, code(response)) == (400, "link_used")
        assert Invitation.objects.get(pk=identifier).status == "revoked"
        assert not CompanyUser.objects.filter(email="colleague@example.test").exists()

    def test_revoking_twice_says_it_is_closed(self):
        _, owner = team()
        client = client_of(owner)
        identifier = invite(client).json()["id"]
        client.delete(f"{INVITES}{identifier}/")
        assert code(client.delete(f"{INVITES}{identifier}/")) == "invitation_closed"


class TestAccepting:
    def test_the_invitee_becomes_a_verified_member_who_can_log_in(self):
        company, owner = team()
        invite(client_of(owner))
        response = accept(last_token(), name="Fake Invitee")
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        member = CompanyUser.objects.get(email="colleague@example.test")
        assert (member.name, member.role, member.company_id) == (
            "Fake Invitee",
            "member",
            company.pk,
        )
        assert member.email_verified and member.terms_accepted_at is not None
        assert Invitation.objects.get().status == "accepted"
        login = APIClient(REMOTE_ADDR="203.0.113.70").post(
            "/api/auth/company/login/",
            {"email": "colleague@example.test", "password": GOOD},
            format="json",
        )
        assert login.status_code == 200 and login.json() == {"status": "ok"}

    def test_the_link_works_only_once(self):
        _, owner = team()
        invite(client_of(owner))
        token = last_token()
        assert accept(token).status_code == 200
        second = accept(token, name="Someone Else")
        assert (second.status_code, code(second)) == (400, "link_used")
        assert CompanyUser.objects.filter(company=owner.company).count() == 2

    def test_a_made_up_link_is_refused(self):
        response = accept("made-up-token-value")
        assert (response.status_code, code(response)) == (400, "link_invalid")

    def test_an_expired_link_is_refused_with_a_clear_message(self):
        _, owner = team()
        invite(client_of(owner))
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = accept(last_token())
        assert (response.status_code, code(response)) == (400, "link_expired")
        assert response.json()["error"]["message"] == "This link has expired."

    def test_a_link_for_something_else_is_refused(self):
        person = make_company_user(email_verified=False)
        other = link_tokens.issue_link_token("verify_email", person.pk, 24)
        assert code(accept(other)) == "link_invalid"

    def test_a_weak_or_mismatched_password_is_refused_and_the_link_is_kept(self):
        _, owner = team()
        invite(client_of(owner))
        token = last_token()
        weak = accept(token, password="short")
        mismatch = accept(token, confirm="another-fresh-password-11")  # nosecret: fake test value
        assert weak.status_code == mismatch.status_code == 400
        assert "password" in weak.json()["error"]["fields"]
        assert "confirm_password" in mismatch.json()["error"]["fields"]
        assert LinkToken.objects.get(purpose="team_invite").used_at is None
        assert accept(token).status_code == 200

    @pytest.mark.parametrize("name", ["", "   ", "x" * 201, "bad\x00name", "a\nb"])
    def test_the_name_must_be_one_line_of_sensible_text(self, name):
        _, owner = team()
        invite(client_of(owner))
        response = accept(last_token(), name=name)
        assert response.status_code == 400 and "name" in response.json()["error"]["fields"]

    def test_an_address_registered_in_the_meantime_is_refused_and_the_link_is_kept(self):
        _, owner = team()
        invite(client_of(owner))
        make_company_user(make_company(), email="colleague@example.test")
        response = accept(last_token())
        assert (response.status_code, code(response)) == (409, "account_exists")
        assert LinkToken.objects.get(purpose="team_invite").used_at is None

    def test_a_suspended_company_cannot_gain_members(self):
        company, owner = team()
        invite(client_of(owner))
        Company.objects.filter(pk=company.pk).update(status="suspended")
        response = accept(last_token())
        assert (response.status_code, code(response)) == (403, "company_suspended")
        assert not CompanyUser.objects.filter(email="colleague@example.test").exists()

    def test_the_password_is_never_in_the_answer_or_the_log(self, project_log):
        _, owner = team()
        invite(client_of(owner))
        response = accept(last_token())
        assert GOOD not in response.content.decode() and GOOD not in project_log.getvalue()


class TestWhoMayDoWhat:
    def test_members_cannot_invite_list_resend_or_revoke(self):
        company, owner = team()
        _, member = team("member", company)
        identifier = invite(client_of(owner)).json()["id"]
        client = client_of(member)
        responses = [
            client.get(INVITES),
            invite(client, "x@example.test"),
            client.post(f"{INVITES}{identifier}/resend/"),
            client.delete(f"{INVITES}{identifier}/"),
        ]
        assert [r.status_code for r in responses] == [403, 403, 403, 403]
        assert Invitation.objects.get(pk=identifier).status == "pending"

    def test_visitors_are_refused(self):
        client = APIClient()
        assert client.get(INVITES).status_code == 401
        assert client.post(INVITES, {"email": "a@example.test"}, format="json").status_code == 401

    def test_another_companys_invitation_looks_like_nothing(self):
        _, owner = team()
        _, other_owner = team()
        identifier = invite(client_of(other_owner), "theirs@example.test").json()["id"]
        client = client_of(owner)
        missing = client.delete(f"{INVITES}00000000-0000-4000-8000-000000000000/")
        resend = client.post(f"{INVITES}{identifier}/resend/")
        revoke = client.delete(f"{INVITES}{identifier}/")
        assert resend.status_code == revoke.status_code == missing.status_code == 404
        assert resend.json() == revoke.json() == missing.json()
        assert Invitation.objects.get(pk=identifier).status == "pending"
        assert "theirs@example.test" not in resend.content.decode()
