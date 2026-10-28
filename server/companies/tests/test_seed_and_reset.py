import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings

from companies.models import Company
from core.errors import AppError


@pytest.mark.django_db
def test_seed_creates_fake_admin_and_company():
    call_command("seed_dev_data")

    admin = get_user_model().objects.get(username="fake-admin")
    assert admin.is_superuser and admin.check_password("FAKE-admin-password-dev-only")
    assert Company.objects.get(name="Fake Test Company").owner.username == "fake-company-owner"


@pytest.mark.django_db
def test_seed_twice_changes_nothing_and_keeps_changed_passwords():
    call_command("seed_dev_data")
    admin = get_user_model().objects.get(username="fake-admin")
    admin.set_password("changed-by-developer")
    admin.save()

    call_command("seed_dev_data")

    assert get_user_model().objects.filter(username="fake-admin").count() == 1
    assert Company.objects.count() == 1
    admin.refresh_from_db()
    assert admin.check_password("changed-by-developer")


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["seed_dev_data", "reset_dev_db"])
def test_development_only_commands_refuse_outside_development(command):
    with override_settings(APP_ENV="production"):
        with pytest.raises(AppError) as caught:
            call_command(command)
    assert caught.value.code == "development_only"
