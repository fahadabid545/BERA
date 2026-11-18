import re
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activity import service as activity
from activity.models import ActivityEntry
from companies.models import CompanyUser, PendingEmailChange
from core.tests.factories import make_company, make_company_user, start_session_for
from cvs.tests.test_ai_reading import set_setting
from emailing.models import LinkToken, OutgoingEmail

pytestmark = pytest.mark.django_db
PROFILE = "/api/company/profile/"
EMAIL = "/api/company/profile/email/"
SETTINGS = "/api/company/settings/"
CONFIRM = "/api/auth/company/confirm-email-change/"
PASSWORD = "A-long-passphrase-9!"


def person_of(company, role="member", **fields):
    person = make_company_user(company, role=role, **fields)
    person.set_password(PASSWORD)
    person.save()
    return person


def client_of(person):
    issued = start_session_for(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def company():
    return make_company()


@pytest.fixture
def owner(company):
    return person_of(company, "owner", name="Olu Owner")


@pytest.fixture
def member(company):
    return person_of(company, "member", name="Mina Member")


def mails(template, to=None):
    """The emails of one kind (addresses are encrypted, so they are matched here)."""
    found = OutgoingEmail.objects.filter(template=template).order_by("created_at")
    return [mail for mail in found if to is None or mail.to_address == to]


def token_in(mail):
    return re.search(r"token=([\w-]+)", mail.text_body).group(1)


class TestProfile:
    def test_it_shows_name_email_role_company_and_country(self, member):
        body = client_of(member).get(PROFILE).json()
        assert body == {
            "name": "Mina Member",
            "email": member.email,
            "role": "member",
            "company_name": member.company.name,
            "country": member.company.country,
        }

    def test_the_name_is_changed_and_trimmed(self, member):
        response = client_of(member).patch(PROFILE, {"name": "  Mina Better  "}, format="json")
        assert response.status_code == 200 and response.json()["name"] == "Mina Better"
        member.refresh_from_db()
        assert member.name == "Mina Better"

    def test_only_the_own_profile_changes(self, member, owner):
        client_of(member).patch(PROFILE, {"name": "New"}, format="json")
        owner.refresh_from_db()
        assert owner.name == "Olu Owner"

    @pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"name": "x" * 201}, {}])
    def test_a_bad_name_is_refused(self, member, body):
        response = client_of(member).patch(PROFILE, body, format="json")
        assert response.status_code == 400 and "name" in response.json()["error"]["fields"]

    @pytest.mark.parametrize("field", ["email", "role", "company_name", "id"])
    def test_nothing_else_can_be_set_here(self, member, field):
        response = client_of(member).patch(PROFILE, {"name": "A", field: "x"}, format="json")
        assert response.status_code == 400
        member.refresh_from_db()
        assert member.role == "member" and member.name == "Mina Member"

    def test_signing_in_is_needed(self):
        assert APIClient().get(PROFILE).status_code == 401
        assert APIClient().patch(PROFILE, {"name": "A"}, format="json").status_code == 401


class TestAskingForAnotherEmail:
    def ask(self, person, email="new@example.com", password=PASSWORD):
        return client_of(person).post(
            EMAIL, {"email": email, "current_password": password}, format="json"
        )

    def test_a_link_goes_to_the_new_address_and_nothing_changes_yet(self, member):
        old = member.email
        response = self.ask(member)
        assert response.status_code == 200
        (mail,) = mails("confirm_new_email")
        assert mail.to_address == "new@example.com"
        assert "/confirm-email-change?token=" in mail.text_body
        member.refresh_from_db()
        assert member.email == old
        assert not mails("email_changed")

    def test_the_address_is_normalised(self, member):
        self.ask(member, " New@Example.COM ")
        assert mails("confirm_new_email")[0].to_address == "new@example.com"
        assert PendingEmailChange.objects.get(person=member).new_email == "new@example.com"

    def test_a_wrong_current_password_sends_nothing(self, member):
        response = self.ask(member, password="not-the-password")
        assert response.status_code == 400
        assert "current_password" in response.json()["error"]["fields"]
        assert not mails("confirm_new_email")
        assert not PendingEmailChange.objects.exists()

    def test_the_same_address_is_refused(self, member):
        response = self.ask(member, member.email.upper())
        assert response.status_code == 400 and "email" in response.json()["error"]["fields"]

    @pytest.mark.parametrize("email", ["", "nope", "a@b", 5])
    def test_a_bad_address_is_refused(self, member, email):
        assert self.ask(member, email).status_code == 400

    def test_a_taken_address_gets_the_same_answer_and_the_account_notice(self, member, owner):
        taken = self.ask(member, owner.email)
        free = self.ask(member, "free@example.com")
        assert taken.status_code == free.status_code == 200
        assert taken.json() == free.json()
        assert len(mails("already_registered", owner.email)) == 1
        assert not mails("confirm_new_email", owner.email)

    def test_a_taken_address_is_not_kept_as_pending(self, member, owner):
        self.ask(member, owner.email)
        assert not PendingEmailChange.objects.exists()

    def test_a_newer_request_replaces_the_older_link(self, member):
        self.ask(member, "first@example.com")
        self.ask(member, "second@example.com")
        first, second = mails("confirm_new_email")
        assert (
            APIClient().post(CONFIRM, {"token": token_in(first)}, format="json").status_code == 400
        )
        assert (
            APIClient().post(CONFIRM, {"token": token_in(second)}, format="json").status_code == 200
        )
        member.refresh_from_db()
        assert member.email == "second@example.com"

    def test_signing_in_is_needed(self):
        response = APIClient().post(EMAIL, {"email": "a@example.com", "current_password": "x"})
        assert response.status_code == 401


class TestConfirmingTheNewAddress:
    @pytest.fixture
    def asked(self, member):
        old = member.email
        client_of(member).post(
            EMAIL, {"email": "new@example.com", "current_password": PASSWORD}, format="json"
        )
        return old, token_in(mails("confirm_new_email")[0])

    def confirm(self, token):
        return APIClient().post(CONFIRM, {"token": token}, format="json")

    def test_the_address_changes_and_counts_as_verified(self, member, asked):
        CompanyUser.objects.filter(pk=member.pk).update(email_verified=False)
        assert self.confirm(asked[1]).status_code == 200
        member.refresh_from_db()
        assert member.email == "new@example.com" and member.email_verified

    def test_the_old_address_is_told(self, member, asked):
        old, token = asked
        self.confirm(token)
        (notice,) = mails("email_changed")
        assert notice.to_address == old

    def test_nothing_is_pending_afterwards(self, member, asked):
        self.confirm(asked[1])
        assert not PendingEmailChange.objects.exists()

    def test_the_link_works_once(self, member, asked):
        assert self.confirm(asked[1]).status_code == 200
        again = self.confirm(asked[1])
        assert again.status_code == 400 and again.json()["error"]["code"] == "link_used"
        assert len(mails("email_changed")) == 1

    def test_an_expired_link_changes_nothing(self, member, asked):
        old, token = asked
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.confirm(token)
        assert response.status_code == 400 and response.json()["error"]["code"] == "link_expired"
        member.refresh_from_db()
        assert member.email == old and not mails("email_changed")

    def test_a_made_up_link_is_refused(self, member, asked):
        assert self.confirm("made-up").status_code == 400

    def test_a_link_for_something_else_is_refused(self, member, asked):
        from emailing.link_tokens import issue_link_token

        other = issue_link_token(LinkToken.Purpose.VERIFY_EMAIL, member.pk, 1)
        assert self.confirm(other).status_code == 400

    def test_an_address_taken_meanwhile_is_refused_and_the_link_stays_usable_for_nobody(
        self, member, asked
    ):
        old, token = asked
        make_company_user(make_company(), email="new@example.com")
        response = self.confirm(token)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "email_unavailable"
        member.refresh_from_db()
        assert member.email == old and not mails("email_changed")

    def test_a_removed_member_cannot_change(self, member, asked):
        CompanyUser.objects.filter(pk=member.pk).update(status="removed")
        assert self.confirm(asked[1]).status_code == 400

    def test_whoever_is_signed_in_plays_no_part(self, member, owner, asked):
        response = client_of(owner).post(CONFIRM, {"token": asked[1]}, format="json")
        assert response.status_code == 200
        owner.refresh_from_db(), member.refresh_from_db()
        assert member.email == "new@example.com" and owner.email != "new@example.com"

    def test_a_missing_token_is_refused(self):
        assert APIClient().post(CONFIRM, {}, format="json").status_code == 400


class TestCompanySettings:
    def test_the_owner_sees_name_country_and_retention(self, owner):
        body = client_of(owner).get(SETTINGS).json()
        assert body["name"] == owner.company.name
        assert body["country"] == owner.company.country
        assert body["retention"] == {
            "days": 180,
            "chosen": None,
            "default_days": 180,
            "choices": [30, 90, 180, 365],
        }

    def test_a_member_is_refused(self, member):
        assert client_of(member).get(SETTINGS).status_code == 403
        assert client_of(member).patch(SETTINGS, {"name": "X"}, format="json").status_code == 403

    def test_signing_in_is_needed(self):
        assert APIClient().get(SETTINGS).status_code == 401

    def test_the_owner_renames_the_company(self, owner):
        response = client_of(owner).patch(SETTINGS, {"name": " New Name "}, format="json")
        assert response.status_code == 200 and response.json()["name"] == "New Name"
        owner.company.refresh_from_db()
        assert owner.company.name == "New Name"

    @pytest.mark.parametrize("body", [{"name": ""}, {"name": "x" * 201}, {}])
    def test_a_bad_change_is_refused(self, owner, body):
        before = owner.company.name
        assert client_of(owner).patch(SETTINGS, body, format="json").status_code == 400
        owner.company.refresh_from_db()
        assert owner.company.name == before

    @pytest.mark.parametrize("field", ["country", "status", "require_two_step"])
    def test_the_billing_country_and_everything_else_is_locked(self, owner, field):
        before = owner.company.country
        response = client_of(owner).patch(SETTINGS, {"name": "A", field: "DE"}, format="json")
        assert response.status_code == 400
        owner.company.refresh_from_db()
        assert owner.company.country == before and owner.company.name != "A"

    def test_another_company_is_never_touched(self, owner):
        other = person_of(make_company(), "owner")
        before = other.company.name
        client_of(owner).patch(SETTINGS, {"name": "Mine", "retention_days": 30}, format="json")
        other.company.refresh_from_db()
        assert other.company.name == before and other.company.retention_days is None

    def test_changes_are_logged_without_the_name(self, owner):
        client_of(owner).patch(SETTINGS, {"name": "Secret Name Ltd"}, format="json")
        (entry,) = ActivityEntry.objects.filter(kind="setting_changed")
        assert entry.details == {"setting": "company_name"} and entry.actor_id == owner.pk


class TestRetentionChoice:
    def choose(self, owner, days):
        return client_of(owner).patch(SETTINGS, {"retention_days": days}, format="json")

    def old_entry(self, owner, days_ago):
        made = activity.record("upload", company_id=owner.company_id, actor=owner)
        ActivityEntry.objects.filter(pk=made.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )

    def uploads(self, client):
        entries = client.get("/api/company/activity/").json()["entries"]
        return [entry for entry in entries if entry["kind"] == "upload"]

    def test_the_default_applies_until_a_choice_is_made(self, owner):
        assert activity.retention_days(owner.company_id) == 180

    @pytest.mark.parametrize("days", [30, 90, 180, 365])
    def test_every_platform_choice_can_be_picked(self, owner, days):
        response = self.choose(owner, days)
        assert response.status_code == 200
        assert response.json()["retention"]["chosen"] == days
        assert activity.retention_days(owner.company_id) == days

    @pytest.mark.parametrize("days", [45, 0, -1, 10000, True])
    def test_anything_else_is_refused(self, owner, days):
        response = self.choose(owner, days)
        assert response.status_code == 400
        assert "retention_days" in response.json()["error"]["fields"]
        assert activity.retention_days(owner.company_id) == 180

    def test_null_goes_back_to_the_platform_default(self, owner):
        self.choose(owner, 30)
        body = self.choose(owner, None).json()
        assert body["retention"]["chosen"] is None and body["retention"]["days"] == 180

    def test_the_activity_list_follows_the_companys_choice(self, owner):
        self.old_entry(owner, 100)
        client = client_of(owner)
        assert len(self.uploads(client)) == 1
        self.choose(owner, 90)
        assert self.uploads(client) == []
        self.choose(owner, 365)
        assert len(self.uploads(client)) == 1

    def test_a_longer_choice_than_the_default_shows_older_entries(self, owner):
        self.old_entry(owner, 200)
        assert self.uploads(client_of(owner)) == []
        self.choose(owner, 365)
        assert len(self.uploads(client_of(owner))) == 1

    def test_another_company_keeps_the_platform_default(self, owner):
        other = person_of(make_company(), "owner")
        self.choose(owner, 30)
        assert activity.retention_days(other.company_id) == 180

    def test_the_purge_follows_each_companys_own_period(self, owner):
        other = person_of(make_company(), "owner")
        self.choose(owner, 30)
        self.old_entry(owner, 60)
        self.old_entry(other, 60)
        self.old_entry(other, 300)
        assert activity.purge_expired_entries() == 3 - 1  # mine at 60 days; the other's at 300
        assert ActivityEntry.objects.filter(company=owner.company).count() == 1  # the log line
        assert ActivityEntry.objects.filter(company=other.company).count() == 1

    def test_a_choice_the_platform_no_longer_offers_falls_back_to_the_default(self, owner):
        self.choose(owner, 30)
        set_setting("retention.choices_days", [90, 180, 365])
        assert activity.retention_days(owner.company_id) == 180
        assert client_of(owner).get(SETTINGS).json()["retention"]["chosen"] is None

    def test_the_change_is_logged(self, owner):
        self.choose(owner, 90)
        (entry,) = ActivityEntry.objects.filter(kind="setting_changed")
        assert entry.details == {"setting": "retention", "days": 90}
