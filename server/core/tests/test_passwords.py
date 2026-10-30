import pytest

from core.passwords import password_problems

# Platform settings are read from the database (admins may override them).
pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("password", ["violet-harbour-lantern-92", "vi0let-harb1", "a" * 11 + "!"])
def test_a_long_enough_uncommon_password_has_no_problems(password):
    assert password_problems(password) == []


def test_eleven_characters_are_too_short():
    assert password_problems("vi0let-harb") == ["Use at least 12 characters."]


@pytest.mark.parametrize(
    "password", ["123456789qwerty", "PASSWORDPASSWORD1"[:0] + "1q2w3e4r5t6y7u"]
)
def test_commonly_used_passwords_are_refused_in_any_capitalisation(password):
    assert any("too common" in problem for problem in password_problems(password.upper()))


def test_every_problem_is_listed():
    assert len(password_problems("qwerty")) == 2


def test_too_long_is_refused():
    assert password_problems("x1" * 70) == ["Use at most 128 characters."]


def test_the_limits_come_from_the_platform_settings(monkeypatch):
    from core import passwords

    values = {
        "passwords.min_length": 20,
        "passwords.max_length": 30,
        "passwords.block_common_passwords": False,
    }
    monkeypatch.setattr(passwords, "get_setting", values.__getitem__)
    assert password_problems("1q2w3e4r5t6y7u") == ["Use at least 20 characters."]
