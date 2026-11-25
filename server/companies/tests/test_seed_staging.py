import pytest
from django.core.management import call_command
from django.test import override_settings

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from core.errors import AppError
from cvs.models import CvFile
from plans.tests.test_limits import make_plan

pytestmark = pytest.mark.django_db


@pytest.fixture
def staging(tmp_path):
    with override_settings(APP_ENV="staging"):
        yield


def test_without_a_plan_it_says_what_to_do_and_adds_no_cvs(staging, capsys):
    call_command("seed_staging_data")
    assert "Create a plan" in capsys.readouterr().out
    assert Company.objects.count() == 1 and CvFile.objects.count() == 0


def test_creates_a_fake_admin_company_and_fake_cvs_with_random_passwords(staging, capsys):
    make_plan(max_projects=5)
    call_command("seed_staging_data")
    shown = capsys.readouterr().out
    assert Company.objects.get().name == "Fake Staging Company"
    assert CompanyUser.objects.get().email == "owner@example.test"
    assert AdminUser.objects.get().email == "admin@example.test"
    assert CvFile.objects.count() == 3
    assert "FAKE-company-password-dev-only" not in shown
    owner_password = [
        line.split(": ")[1] for line in shown.splitlines() if "owner password" in line
    ]
    assert CompanyUser.objects.get().check_password(owner_password[0])


def test_running_twice_changes_nothing_and_prints_no_password_again(staging, capsys):
    make_plan(max_projects=5)
    call_command("seed_staging_data")
    capsys.readouterr()
    call_command("seed_staging_data")
    assert "password" not in capsys.readouterr().out.replace("Fake staging data is ready.", "")
    assert Company.objects.count() == 1 and CvFile.objects.count() == 3


@pytest.mark.parametrize("env", ["production", "development"])
def test_refuses_outside_staging(env):
    with override_settings(APP_ENV=env):
        with pytest.raises(AppError) as caught:
            call_command("seed_staging_data")
    assert caught.value.code == "staging_only"
    assert not Company.objects.exists()
