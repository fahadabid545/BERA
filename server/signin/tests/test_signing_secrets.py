import pytest

from config.environment import require_signing_secrets
from core.errors import ConfigurationError

GOOD = {
    "JWT_COMPANY_SECRET": "fake-company-signing-secret-0123456789",
    "JWT_ADMIN_SECRET": "fake-admin-signing-secret-9876543210x",
}


def test_two_long_different_secrets_are_accepted():
    assert require_signing_secrets(GOOD) == {
        "company": GOOD["JWT_COMPANY_SECRET"],
        "admin": GOOD["JWT_ADMIN_SECRET"],
    }


@pytest.mark.parametrize("name", GOOD)
def test_a_missing_secret_stops_start_up(name):
    with pytest.raises(ConfigurationError) as caught:
        require_signing_secrets({**GOOD, name: ""})
    assert name in caught.value.message


@pytest.mark.parametrize("name", GOOD)
def test_a_short_secret_stops_start_up_without_revealing_it(name):
    with pytest.raises(ConfigurationError) as caught:
        require_signing_secrets({**GOOD, name: "too-short"})
    assert name in caught.value.message and "too-short" not in caught.value.message


def test_the_same_secret_for_both_kinds_stops_start_up():
    with pytest.raises(ConfigurationError):
        require_signing_secrets({**GOOD, "JWT_ADMIN_SECRET": GOOD["JWT_COMPANY_SECRET"]})
