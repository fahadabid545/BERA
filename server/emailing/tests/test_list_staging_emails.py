import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from emailing.samples import sample_values
from emailing.service import send_email

pytestmark = pytest.mark.django_db


@pytest.fixture
def folder(tmp_path):
    with override_settings(
        APP_ENV="staging",
        EMAIL_BACKEND="emailing.backends.DevInboxBackend",
        EMAIL_FILE_PATH=tmp_path,
    ):
        yield tmp_path


def out(capsys, *args):
    call_command("list_staging_emails", *args)
    return capsys.readouterr().out


def test_says_so_when_nothing_was_saved(folder, capsys):
    assert "No saved emails." in out(capsys)


def test_lists_saved_emails_and_shows_one(folder, capsys):
    send_email("verify_email", "tester@example.test", now=True, **sample_values("verify_email"))
    listing = out(capsys)
    assert "tester@example.test" in listing and "Verify your email" in listing
    name = listing.split()[0]
    shown = out(capsys, "--show", name)
    assert "Subject: Verify your email" in shown


def test_show_takes_a_file_name_never_a_path(folder, capsys):
    with pytest.raises(CommandError):
        call_command("list_staging_emails", "--show", "../../etc/passwd")
    with pytest.raises(CommandError):
        call_command("list_staging_emails", "--show", "missing.eml")


def test_refuses_in_production(tmp_path):
    with override_settings(APP_ENV="production", EMAIL_FILE_PATH=tmp_path):
        with pytest.raises(CommandError):
            call_command("list_staging_emails")
