import hashlib
import logging
import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from companies.models import Company, CompanyUser
from core.tests.factories import make_company_user
from emailing.models import LinkToken, OutgoingEmail
from emailing.service import deliver_email

URL = "/api/auth/company/signup/"
NEUTRAL = "If this email can be used, we have sent instructions."
STRONG = "violet-harbour-lantern-92"
VALID = {
    "company_name": "Fake Test Ltd",
    "name": "Fake Owner",
    "email": "owner@example.test",
    "password": STRONG,
    "country": "DE",
    "accept_terms": True,
}

pytestmark = pytest.mark.django_db


def sign_up(client=None, address="203.0.113.10", **changes):
    body = {**VALID, **changes}
    body = {name: value for name, value in body.items() if value is not None}
    client = client or APIClient(REMOTE_ADDR=address)
    return client.post(URL, body, format="json")


def sent_emails():
    emails = list(OutgoingEmail.objects.filter(status="queued"))
    texts = []
    for email in emails:
        texts.append((email.template, email.to_address, email.text_body))
        deliver_email(str(email.id))
    return texts


class TestCreatingTheAccount:
    def test_it_creates_the_company_and_its_owner(self):
        response = sign_up()
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "message": NEUTRAL}
        company = Company.objects.get()
        assert (company.name, company.country, company.status) == ("Fake Test Ltd", "DE", "active")
        owner = CompanyUser.objects.get()
        assert (owner.company, owner.name, owner.email) == (company, "Fake Owner", VALID["email"])
        assert (owner.role, owner.status) == ("owner", "active")

    def test_the_owner_cannot_use_the_panel_until_the_email_is_verified(self):
        sign_up()
        assert CompanyUser.objects.get().email_verified is False

    def test_the_time_the_terms_were_accepted_is_recorded(self):
        before = timezone.now()
        sign_up()
        assert before <= CompanyUser.objects.get().terms_accepted_at <= timezone.now()

    def test_the_password_is_stored_only_as_a_strong_hash(self):
        sign_up()
        owner = CompanyUser.objects.get()
        assert owner.password_hash.startswith("argon2$") and STRONG not in owner.password_hash
        assert owner.check_password(STRONG)

    def test_the_email_is_saved_trimmed_and_in_lower_case(self):
        sign_up(email="  Owner@Example.TEST ")
        assert CompanyUser.objects.get().email == "owner@example.test"

    def test_the_country_defaults_to_other(self):
        sign_up(country=None)
        assert Company.objects.get().country == "ZZ"

    def test_the_visitor_may_choose_other_explicitly(self):
        sign_up(country="ZZ")
        assert Company.objects.get().country == "ZZ"

    def test_nothing_in_the_answer_reveals_the_new_account(self):
        text = sign_up().content.decode()
        assert "owner@example.test" not in text and STRONG not in text


class TestTheVerificationEmail:
    def test_one_verification_email_is_sent_to_the_new_owner(self):
        sign_up()
        assert [(template, to) for template, to, _ in sent_emails()] == [
            ("verify_email", VALID["email"])
        ]
        (message,) = mail.outbox
        assert message.to == [VALID["email"]] and "Verify" in message.subject

    def test_its_link_holds_a_random_single_purpose_token_stored_only_hashed(self):
        sign_up()
        ((_, _, text),) = sent_emails()
        token = re.search(r"/verify-email\?token=([\w-]+)", text).group(1)
        stored = LinkToken.objects.get()
        assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in stored.token_hash and len(token) >= 40
        assert (
            stored.purpose == "verify_email" and stored.subject_id == CompanyUser.objects.get().pk
        )
        assert stored.used_at is None

    def test_the_link_works_for_24_hours(self):
        sign_up()
        stored = LinkToken.objects.get()
        assert (
            timedelta(hours=23, minutes=59)
            < stored.expires_at - timezone.now()
            <= timedelta(hours=24)
        )

    def test_two_sign_ups_get_different_tokens(self):
        sign_up()
        sign_up(email="second@example.test", company_name="Second Fake Ltd")
        assert LinkToken.objects.values("token_hash").distinct().count() == 2


class TestAnEmailThatIsAlreadyRegistered:
    def existing(self, **fields):
        return make_company_user(email="owner@example.test", name="Existing Person", **fields)

    def test_the_visitor_sees_exactly_the_same_answer(self):
        fresh = sign_up(email="new.person@example.test")
        taken = self.existing()
        again = sign_up(email=taken.email)
        assert (again.status_code, again.content) == (fresh.status_code, fresh.content)

    @pytest.mark.parametrize(
        "typed", ["owner@example.test", "OWNER@Example.test", " owner@example.test "]
    )
    def test_in_any_spelling(self, typed):
        self.existing()
        assert sign_up(email=typed).json()["message"] == NEUTRAL

    def test_no_second_account_is_created(self):
        self.existing()
        companies_before = Company.objects.count()
        sign_up()
        assert CompanyUser.objects.count() == 1 and Company.objects.count() == companies_before
        assert not LinkToken.objects.exists()

    def test_the_existing_person_gets_a_notice_instead_of_a_verification_email(self):
        self.existing()
        sign_up()
        ((template, to, text),) = sent_emails()
        assert (template, to) == ("already_registered", "owner@example.test")
        assert "Existing Person" in text and "/login" in text and "token" not in text

    @pytest.mark.parametrize("status", ["active", "blocked", "removed"])
    def test_whatever_the_status_of_the_existing_person(self, status):
        self.existing(status=status, role="member")
        assert sign_up().json()["message"] == NEUTRAL
        assert [template for template, _, _ in sent_emails()] == ["already_registered"]

    def test_the_notices_to_one_inbox_are_limited(self):
        self.existing()
        for number in range(6):
            sign_up(address=f"203.0.113.{number + 20}")
        assert OutgoingEmail.objects.filter(template="already_registered").count() == 3

    def test_the_answer_stays_the_same_when_the_notice_limit_is_reached(self):
        self.existing()
        answers = {sign_up(address=f"203.0.113.{n + 20}").content for n in range(5)}
        assert len(answers) == 1

    def test_a_clash_at_the_last_moment_is_handled_the_same_way(self, monkeypatch):
        from companies import signup

        self.existing()
        # The check ran just before the other sign-up was saved, so it found nothing.
        monkeypatch.setattr(signup, "_email_is_taken", lambda email: False)
        assert sign_up().json()["message"] == NEUTRAL
        assert CompanyUser.objects.count() == 1 and not LinkToken.objects.exists()
        assert Company.objects.count() == 1
        assert [t for t, _, _ in sent_emails()] == ["already_registered"]


class TestWeakPasswords:
    def message(self, response):
        return response.json()["error"]["fields"]["password"]

    def test_a_short_password_is_refused_with_the_reason(self):
        response = sign_up(password="Sh0rt-one")
        assert response.status_code == 400
        assert self.message(response) == "Use at least 12 characters."

    def test_a_common_password_is_refused_with_the_reason(self):
        response = sign_up(password="123456789qwerty")
        assert response.status_code == 400
        assert "too common" in self.message(response)

    def test_every_reason_is_shown_at_once(self):
        response = sign_up(password="password")
        message = self.message(response)
        assert "at least 12 characters" in message and "too common" in message

    def test_a_very_long_password_is_refused(self):
        response = sign_up(password="a1" * 70)
        assert "at most 128 characters" in self.message(response)

    def test_a_password_of_twelve_characters_is_enough(self):
        assert sign_up(password="vi0let-harb1").status_code == 200

    @pytest.mark.parametrize("password", [123456789012, ["a-long-enough-password"], None, True])
    def test_a_password_that_is_not_text_is_refused(self, password):
        body = {**VALID, "password": password}
        response = APIClient(REMOTE_ADDR="203.0.113.10").post(URL, body, format="json")
        assert response.status_code == 400 and "password" in response.json()["error"]["fields"]

    def test_nothing_is_created_or_sent(self):
        sign_up(password="short")
        assert not Company.objects.exists() and not OutgoingEmail.objects.exists()

    def test_it_is_refused_the_same_way_for_an_email_that_is_already_registered(self):
        make_company_user(email="owner@example.test")
        response = sign_up(password="short")
        assert response.status_code == 400
        assert not OutgoingEmail.objects.exists()

    def test_the_password_is_never_echoed_or_logged(self, caplog):
        with caplog.at_level(logging.DEBUG):
            response = sign_up(password="Sh0rt-one")
            sign_up()
        assert "Sh0rt-one" not in response.content.decode() + caplog.text
        assert STRONG not in caplog.text and "owner@example.test" not in caplog.text


class TestTheTermsAndTheOtherFields:
    @pytest.mark.parametrize("accepted", [False, None, "no", 0, "false"])
    def test_the_terms_must_be_ticked(self, accepted):
        response = sign_up(accept_terms=accepted)
        assert response.status_code == 400
        assert "accept_terms" in response.json()["error"]["fields"]
        assert not Company.objects.exists()

    def test_the_message_for_unticked_terms(self):
        fields = sign_up(accept_terms=False).json()["error"]["fields"]
        assert fields["accept_terms"] == "Accept the Terms and Privacy Policy to continue."

    @pytest.mark.parametrize("field", ["company_name", "name", "email", "password"])
    def test_every_field_is_required(self, field):
        response = sign_up(**{field: None})
        assert response.status_code == 400 and field in response.json()["error"]["fields"]

    @pytest.mark.parametrize(
        "email", ["not-an-email", "a@", "@b.test", "a b@example.test", "x" * 250 + "@example.test"]
    )
    def test_the_email_must_look_like_an_email(self, email):
        assert "email" in sign_up(email=email).json()["error"]["fields"]

    @pytest.mark.parametrize("country", ["XX", "de", "Germany", "T1", "", 49])
    def test_the_country_must_be_a_known_code(self, country):
        assert "country" in sign_up(country=country).json()["error"]["fields"]

    @pytest.mark.parametrize("field", ["company_name", "name"])
    @pytest.mark.parametrize("value", ["x" * 201, "line\nbreak", "nul\x00byte", "   "])
    def test_names_must_be_plain_text_of_a_sensible_length(self, field, value):
        assert field in sign_up(**{field: value}).json()["error"]["fields"]

    def test_fields_that_do_not_exist_are_refused(self):
        response = sign_up(role="owner", email_verified=True)
        assert response.status_code == 400
        assert not Company.objects.exists()

    def test_every_mistake_is_reported_together(self):
        fields = sign_up(name=None, password="short", accept_terms=False).json()["error"]["fields"]
        assert set(fields) == {"name", "password", "accept_terms"}


class TestRepeatedSignUps:
    def test_the_sixth_attempt_in_an_hour_from_one_address_is_slowed_down(self):
        statuses = [sign_up(email=f"person{n}@example.test").status_code for n in range(6)]
        assert statuses == [200] * 5 + [429]

    def test_the_answer_says_when_to_try_again(self):
        for n in range(5):
            sign_up(email=f"person{n}@example.test")
        response = sign_up(email="person5@example.test")
        assert int(response["Retry-After"]) > 0
        assert response.json()["error"]["code"] == "too_many_requests"
        assert not CompanyUser.objects.filter(email="person5@example.test").exists()

    def test_failed_attempts_count_too(self):
        for _ in range(5):
            sign_up(password="short")
        assert sign_up().status_code == 429

    def test_another_address_is_not_affected(self):
        for n in range(6):
            sign_up(email=f"person{n}@example.test")
        assert sign_up(address="198.51.100.7").status_code == 200

    def test_the_limit_is_the_platform_setting(self, settings):
        from core import rate_limits

        assert rate_limits.SIGN_UP.setting_key == "rate_limits.sign_up_per_hour"
