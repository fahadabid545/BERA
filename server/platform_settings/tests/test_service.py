import logging

import pytest
from django.db import OperationalError

from core.errors import AppError
from platform_settings import service
from platform_settings.models import PlatformSetting

KEY = "team.max_accounts_per_company"
DEFAULT = 3


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(service, "_values", None)
    monkeypatch.setattr(service, "_loaded_at", 0.0)
    monkeypatch.setattr(service, "_last_warned_at", {})


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 1000.0

        def advance(self, seconds):
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr(service, "_now", lambda: clock.now)
    return clock


@pytest.mark.django_db
def test_empty_table_uses_defaults_without_warnings(caplog):
    with caplog.at_level(logging.WARNING):
        assert service.get_setting(KEY) == DEFAULT
        assert service.get_setting("uploads.allowed_file_types") == ["pdf", "docx"]
    assert caplog.records == []


@pytest.mark.django_db
def test_stored_override_is_used():
    PlatformSetting.objects.create(key=KEY, value=5)
    assert service.get_setting(KEY) == 5


@pytest.mark.django_db
def test_saving_a_change_applies_immediately_and_deleting_restores_default():
    assert service.get_setting(KEY) == DEFAULT
    row = PlatformSetting.objects.create(key=KEY, value=5)
    assert service.get_setting(KEY) == 5
    row.value = 8
    row.save()
    assert service.get_setting(KEY) == 8
    row.delete()
    assert service.get_setting(KEY) == DEFAULT


@pytest.mark.django_db
def test_change_made_behind_the_apps_back_appears_after_the_cache_expires(clock):
    assert service.get_setting(KEY) == DEFAULT
    PlatformSetting.objects.bulk_create([PlatformSetting(key=KEY, value=5)])

    clock.advance(service.CACHE_SECONDS - 1)
    assert service.get_setting(KEY) == DEFAULT
    clock.advance(1)
    assert service.get_setting(KEY) == 5


@pytest.mark.django_db
@pytest.mark.parametrize("bad_value", ["5", 5.5, True, 0, 100000, [5]])
def test_invalid_stored_value_falls_back_to_default_and_warns(bad_value, caplog):
    PlatformSetting.objects.create(key=KEY, value=bad_value)
    with caplog.at_level(logging.WARNING):
        assert service.get_setting(KEY) == DEFAULT
    assert [record.getMessage() for record in caplog.records] == [
        f"Ignoring stored setting '{KEY}': its value is not allowed. Using default."
    ]


@pytest.mark.django_db
def test_unknown_stored_setting_is_ignored_with_a_warning(caplog):
    PlatformSetting.objects.create(key="no.such_setting", value=1)
    with caplog.at_level(logging.WARNING):
        assert service.get_setting(KEY) == DEFAULT
    assert "no.such_setting" in caplog.text


@pytest.mark.django_db
def test_one_invalid_value_does_not_affect_other_settings():
    PlatformSetting.objects.create(key=KEY, value="bad")
    PlatformSetting.objects.create(key="uploads.max_file_size_mb", value=20)
    assert service.get_setting(KEY) == DEFAULT
    assert service.get_setting("uploads.max_file_size_mb") == 20


@pytest.mark.django_db
def test_the_warning_is_logged_once_per_setting_per_hour(clock, caplog):
    PlatformSetting.objects.create(key=KEY, value="bad")
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            service.get_setting(KEY)
            clock.advance(service.CACHE_SECONDS)
        assert len(caplog.records) == 1
        clock.advance(service.WARNING_INTERVAL_SECONDS)
        service.get_setting(KEY)
        assert len(caplog.records) == 2


@pytest.mark.django_db
def test_stored_values_are_not_written_to_logs(caplog):
    PlatformSetting.objects.create(key=KEY, value="sensitive-looking-text")
    with caplog.at_level(logging.WARNING):
        service.get_setting(KEY)
    assert "sensitive-looking-text" not in caplog.text


def break_database(monkeypatch):
    def unreachable():
        raise OperationalError("connection refused")

    monkeypatch.setattr(service, "_read_overrides", unreachable)


@pytest.mark.django_db
def test_database_down_at_first_read_uses_defaults_and_warns(monkeypatch, caplog):
    break_database(monkeypatch)
    with caplog.at_level(logging.WARNING):
        assert service.get_setting(KEY) == DEFAULT
    assert "could not be read" in caplog.text


@pytest.mark.django_db
def test_database_down_later_keeps_last_known_good_values(monkeypatch, clock, caplog):
    PlatformSetting.objects.create(key=KEY, value=5)
    assert service.get_setting(KEY) == 5

    break_database(monkeypatch)
    clock.advance(service.CACHE_SECONDS)
    with caplog.at_level(logging.WARNING):
        assert service.get_setting(KEY) == 5
    assert "could not be read" in caplog.text


@pytest.mark.django_db
def test_database_recovering_picks_up_stored_values_again(monkeypatch, clock):
    PlatformSetting.objects.create(key=KEY, value=5)
    with monkeypatch.context() as broken:
        break_database(broken)
        assert service.get_setting(KEY) == DEFAULT
    clock.advance(service.CACHE_SECONDS)
    assert service.get_setting(KEY) == 5


def test_unknown_setting_requested_by_code_is_an_error():
    with pytest.raises(AppError) as caught:
        service.get_setting("typo.setting")
    assert caught.value.code == "unknown_setting"


@pytest.mark.django_db
def test_changing_a_returned_list_does_not_change_the_setting():
    service.get_setting("uploads.allowed_file_types").append("exe")
    assert service.get_setting("uploads.allowed_file_types") == ["pdf", "docx"]
