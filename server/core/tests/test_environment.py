import pytest
from config.environment import app_environment, require_settings

from core.errors import ConfigurationError


@pytest.mark.parametrize("name", ["development", "staging", "production"])
def test_app_environment_accepts_known_names(name):
    assert app_environment({"APP_ENV": name}) == name


@pytest.mark.parametrize("environ", [{}, {"APP_ENV": ""}, {"APP_ENV": "prod"}])
def test_app_environment_refuses_missing_or_unknown_name(environ):
    with pytest.raises(ConfigurationError):
        app_environment(environ)


def test_require_settings_returns_values():
    assert require_settings(["A"], {"A": " value "}) == {"A": "value"}


def test_require_settings_lists_every_missing_name_but_no_values():
    environ = {"DJANGO_SECRET_KEY": "super-secret", "DATABASE_URL": "  "}
    with pytest.raises(ConfigurationError) as caught:
        require_settings(["DJANGO_SECRET_KEY", "DATABASE_URL", "ALLOWED_HOSTS"], environ)
    assert caught.value.details == {"missing": ["DATABASE_URL", "ALLOWED_HOSTS"]}
    assert "super-secret" not in caught.value.message
