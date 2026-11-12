from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from adminusers.first_super_admin import ALREADY_SET_UP, create_first_super_admin
from adminusers.models import AdminUser
from core.errors import AppError
from core.tests.factories import make_admin_user

PASSWORD = "violet-harbour-lantern-92"  # nosecret: fake test value
pytestmark = pytest.mark.django_db


def run_command(*typed, name="Fake Boss", email="Boss@Example.test "):
    output = StringIO()
    with patch("getpass.getpass", side_effect=list(typed)):
        call_command("create_first_super_admin", name=name, email=email, stdout=output)
    return output.getvalue()


class TestTheFirstSuperAdmin:
    def test_it_makes_one_super_admin_with_a_hashed_password_and_no_authenticator_yet(self):
        run_command(PASSWORD, PASSWORD)
        admin = AdminUser.objects.get()
        assert admin.role == "super" and admin.status == "active"
        assert admin.email == "boss@example.test"
        assert admin.password_hash.startswith("argon2$") and admin.check_password(PASSWORD)
        assert not admin.two_step_enabled and admin.two_step_secret == ""

    def test_it_works_only_once(self):
        run_command(PASSWORD, PASSWORD)
        with pytest.raises(CommandError, match=ALREADY_SET_UP):
            run_command(PASSWORD, PASSWORD, email="second@example.test")
        assert AdminUser.objects.count() == 1

    def test_any_existing_admin_stops_it_even_a_removed_one(self):
        make_admin_user(status="removed")
        with pytest.raises(AppError) as error:
            create_first_super_admin(name="Fake", email="late@example.test", password=PASSWORD)
        assert error.value.code == "admin_exists"
        assert AdminUser.objects.count() == 1

    def test_a_weak_password_is_refused_with_the_same_rules_as_everywhere(self):
        with pytest.raises(CommandError):
            run_command("short", "short")
        assert not AdminUser.objects.exists()

    def test_two_different_passwords_are_refused(self):
        with pytest.raises(CommandError, match="not the same"):
            run_command(PASSWORD, PASSWORD + "x")
        assert not AdminUser.objects.exists()

    def test_the_password_is_asked_for_at_a_hidden_prompt_and_never_printed(self):
        output = run_command(PASSWORD, PASSWORD)
        assert PASSWORD not in output

    def test_the_password_cannot_be_given_as_an_option(self):
        with pytest.raises(TypeError):  # Django refuses an option the command does not have
            call_command("create_first_super_admin", name="X", email="x@example.test", password="p")
