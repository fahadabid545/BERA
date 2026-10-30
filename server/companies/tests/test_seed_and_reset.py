import pytest
from django.core.management import call_command
from django.test import override_settings

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from core.errors import AppError


@pytest.mark.django_db
def test_seed_creates_fake_admin_and_company_with_its_owner():
    call_command("seed_dev_data")

    admin = AdminUser.objects.get(email="admin@example.test")
    assert admin.role == "super" and admin.check_password("FAKE-admin-password-dev-only")
    owner = CompanyUser.objects.get(company__name="Fake Test Company")
    assert owner.role == "owner" and owner.email_verified
    assert owner.check_password("FAKE-company-password-dev-only")


@pytest.mark.django_db
def test_seed_twice_changes_nothing_and_keeps_changed_passwords():
    call_command("seed_dev_data")
    admin = AdminUser.objects.get(email="admin@example.test")
    admin.set_password("changed-by-developer")
    admin.save()

    call_command("seed_dev_data")

    assert AdminUser.objects.count() == 1
    assert Company.objects.count() == 1 and CompanyUser.objects.count() == 1
    admin.refresh_from_db()
    assert admin.check_password("changed-by-developer")


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["seed_dev_data", "reset_dev_db"])
def test_development_only_commands_refuse_outside_development(command):
    with override_settings(APP_ENV="production"):
        with pytest.raises(AppError) as caught:
            call_command(command)
    assert caught.value.code == "development_only"
