import pytest
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db
URL = "/api/auth/company/signup/country/"
THROUGH_PROXY = {"HTTP_X_FORWARDED_FOR": "198.51.100.7"}


def country(header=None, *, forwarded=True, **settings):
    extra = dict(THROUGH_PROXY) if forwarded else {}
    if header is not None:
        extra["HTTP_CF_IPCOUNTRY"] = header
    behind_a_proxy = {"APP_ENV": "production", "TRUSTED_PROXY_COUNT": 1, **settings}
    with override_settings(**behind_a_proxy):
        response = APIClient(REMOTE_ADDR="10.0.0.2").get(URL, **extra)
    assert response.status_code == 200
    return response.json()["country"]


class TestBehindOurProxy:
    @pytest.mark.parametrize(("sent", "wanted"), [("PK", "PK"), ("de", "DE"), (" us ", "US")])
    def test_the_cloudflare_country_is_used(self, sent, wanted):
        assert country(sent) == wanted

    @pytest.mark.parametrize("sent", ["XX", "T1", "ZZ", "", "Pakistan", "P", "12", "A1", "P K"])
    def test_unknown_and_special_values_become_other(self, sent):
        assert country(sent) == "ZZ"

    def test_no_header_means_other(self):
        assert country() == "ZZ"

    def test_the_development_setting_is_ignored(self):
        assert country("DE", DEVELOPMENT_PRETEND_COUNTRY="PK") == "DE"
        assert country(DEVELOPMENT_PRETEND_COUNTRY="PK") == "ZZ"


class TestNotBehindOurProxy:
    def test_a_header_written_by_the_visitor_is_not_believed(self):
        assert country("PK", forwarded=False) == "ZZ"

    def test_it_is_not_believed_when_no_proxy_is_configured(self):
        assert country("PK", TRUSTED_PROXY_COUNT=0) == "ZZ"


class TestInDevelopment:
    def test_without_the_setting_it_is_other_even_if_a_header_is_sent(self):
        response = APIClient().get(URL, HTTP_CF_IPCOUNTRY="PK")
        assert response.json() == {"country": "ZZ"}

    def test_the_setting_pretends_a_country(self):
        with override_settings(DEVELOPMENT_PRETEND_COUNTRY="PK"):
            assert APIClient().get(URL).json() == {"country": "PK"}


def test_it_needs_no_account_and_nothing_else_is_returned():
    response = APIClient().get(URL)
    assert response.status_code == 200 and set(response.json()) == {"country"}
