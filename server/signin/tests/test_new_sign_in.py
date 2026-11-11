import pytest
from rest_framework.test import APIClient

from companies.account_notices import send_email_changed_notice
from core.tests.factories import make_company_user
from emailing.models import OutgoingEmail
from signin.devices import UNKNOWN_DEVICE, describe_device
from signin.models import KnownSignIn
from signin.new_sign_in import UNKNOWN_PLACE, place_name

LOGIN = "/api/auth/company/login/"
PASSWORD = "violet-harbour-lantern-92"  # nosecret: fake test value
FIREFOX_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
pytestmark = pytest.mark.django_db


@pytest.fixture
def account():
    account = make_company_user(email="owner@example.test", name="Fake Owner", email_verified=True)
    account.set_password(PASSWORD)
    account.save()
    return account


def log_in(agent=FIREFOX_WINDOWS, country=None):
    headers = {"HTTP_USER_AGENT": agent}
    if country:
        headers["HTTP_CF_IPCOUNTRY"] = country
    response = APIClient(REMOTE_ADDR="203.0.113.10", **headers).post(
        LOGIN, {"email": "owner@example.test", "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200
    return response


def notices():
    return OutgoingEmail.objects.filter(template="new_sign_in")


@pytest.fixture(autouse=True)
def pretend_country(settings):
    # Development has no Cloudflare header, so the country is pretended by this setting.
    settings.DEVELOPMENT_PRETEND_COUNTRY = "DE"


class TestTheDeviceDescription:
    @pytest.mark.parametrize(
        ("agent", "expected"),
        [
            (FIREFOX_WINDOWS, "Firefox on Windows"),
            (CHROME_MAC, "Chrome on Mac"),
            (
                "Mozilla/5.0 (Windows NT 10.0) Chrome/129.0 Safari/537.36 Edg/129.0",
                "Edge on Windows",
            ),
            (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Version/17.0 Safari/604.1",
                "Safari on iPhone",
            ),
            (
                "Mozilla/5.0 (Linux; Android 14) Chrome/129.0 Mobile Safari/537.36",
                "Chrome on Android",
            ),
            ("", UNKNOWN_DEVICE),
            ("curl/8.0", UNKNOWN_DEVICE),
        ],
    )
    def test_it_names_the_browser_and_system(self, agent, expected):
        assert describe_device(agent) == expected

    def test_a_browser_update_is_not_a_new_device(self):
        newer = FIREFOX_WINDOWS.replace("130.0", "140.0")
        assert describe_device(newer) == describe_device(FIREFOX_WINDOWS)

    def test_a_huge_or_hostile_value_cannot_break_it(self):
        assert describe_device("A" * 100000) == UNKNOWN_DEVICE
        assert describe_device(None) == UNKNOWN_DEVICE


class TestTheNotice:
    def test_the_first_sign_in_is_the_baseline_and_sends_nothing(self, account):
        log_in()
        assert not notices().exists()
        assert KnownSignIn.objects.filter(user=account).count() == 1

    def test_the_same_device_and_place_again_sends_nothing(self, account):
        log_in()
        log_in()
        assert not notices().exists() and KnownSignIn.objects.count() == 1

    def test_a_new_device_sends_a_notice(self, account):
        log_in()
        log_in(agent=CHROME_MAC)
        assert notices().count() == 1

    def test_a_new_country_sends_a_notice(self, account, settings):
        log_in()
        settings.DEVELOPMENT_PRETEND_COUNTRY = "PK"
        log_in()
        assert notices().count() == 1

    def test_returning_to_a_known_device_and_place_is_quiet(self, account):
        log_in()
        log_in(agent=CHROME_MAC)
        log_in(agent=FIREFOX_WINDOWS)
        log_in(agent=CHROME_MAC)
        assert notices().count() == 1

    def test_the_notice_names_the_device_and_the_country_and_goes_to_the_person(
        self, account, settings
    ):
        log_in()
        settings.DEVELOPMENT_PRETEND_COUNTRY = "PK"
        log_in(agent=CHROME_MAC)
        sent = notices().get()
        assert "Chrome on Mac" in sent.text_body and "Pakistan" in sent.text_body
        assert sent.to_address == "owner@example.test"

    def test_an_unknown_country_is_described_in_words(self):
        assert place_name("ZZ") == UNKNOWN_PLACE and place_name("DE") == "Germany"

    def test_no_address_is_stored(self, account):
        log_in()
        row = KnownSignIn.objects.get()
        assert set(vars(row)) >= {"device", "country"} and "203.0.113" not in str(vars(row))

    def test_a_wrong_password_records_and_sends_nothing(self, account):
        APIClient().post(LOGIN, {"email": "owner@example.test", "password": "wrong"}, format="json")
        assert not KnownSignIn.objects.exists() and not notices().exists()

    def test_a_sign_in_with_two_step_sends_the_notice_after_the_code(self, account):
        from twostep.tests.helpers import code_at, turn_on

        secret, _ = turn_on(account)
        KnownSignIn.objects.create(user=account, device="Firefox on Windows", country="DE")
        challenge = (
            APIClient(REMOTE_ADDR="203.0.113.10", HTTP_USER_AGENT=CHROME_MAC)
            .post(LOGIN, {"email": "owner@example.test", "password": PASSWORD}, format="json")
            .json()["challenge"]
        )
        assert not notices().exists()  # the password alone is not a sign-in yet
        APIClient(REMOTE_ADDR="203.0.113.10", HTTP_USER_AGENT=CHROME_MAC).post(
            "/api/auth/company/login/two-step/",
            {"challenge": challenge, "code": code_at(secret, 1)},
            format="json",
        )
        assert notices().count() == 1


class TestTheOtherTwoNotices:
    def test_changing_the_password_sends_the_notice(self, account):
        client = APIClient(REMOTE_ADDR="203.0.113.10")
        client.post(LOGIN, {"email": "owner@example.test", "password": PASSWORD}, format="json")
        csrf = client.cookies["bera_csrf"].value
        response = client.post(
            "/api/auth/company/change-password/",
            {
                "current_password": PASSWORD,
                "password": "copper-meadow-lantern-58",  # nosecret: fake test value
                "confirm_password": "copper-meadow-lantern-58",  # nosecret: fake test value
            },
            format="json",
            HTTP_X_CSRF_TOKEN=csrf,
        )
        assert response.status_code == 200
        assert OutgoingEmail.objects.filter(template="password_changed").count() == 1

    def test_the_email_changed_notice_goes_to_the_address_the_person_had_before(self, account):
        account.email = "new-address@example.test"
        account.save()
        send_email_changed_notice(account, "owner@example.test")
        sent = OutgoingEmail.objects.get(template="email_changed")
        assert sent.to_address == "owner@example.test"
        assert "contact support" in sent.text_body.lower()
        assert "new-address@example.test" not in sent.text_body
