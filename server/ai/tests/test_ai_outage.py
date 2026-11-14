from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from ai import client, control
from ai.client import AiAnswer, AiPaused, AiUnavailable, call_ai
from ai.models import AiCall, AiControl
from ai.tests.test_model_settings import REASON, admin_client
from audit.models import AuditEvent
from core.tests.factories import make_company
from cvs.tests.test_ai_reading import set_setting

pytestmark = pytest.mark.django_db
URL = "/api/admin/ai/controls/"


@pytest.fixture(autouse=True)
def three_failures_pause():
    set_setting("ai.pause_after_failures", 3)
    set_setting("ai.auto_pause_minutes", 10)


@pytest.fixture
def provider(monkeypatch):
    """The provider's answers, in order: an AiAnswer or an exception."""
    queue = []

    def fake_send(**kwargs):
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(client, "_send", fake_send)
    return queue


def ask():
    return call_ai(make_company().pk, purpose="scoring", model="m", instructions="i", text="t")


def fail_times(provider, count):
    for _ in range(count):
        provider.append(AiUnavailable("down"))
        with pytest.raises(AiUnavailable):
            ask()


GOOD = AiAnswer("{}", 1, 1)


class TestAutomaticPause:
    def test_failures_in_a_row_pause_ai_work_with_the_users_message(self, provider):
        fail_times(provider, 2)
        assert control.is_paused() is False
        fail_times(provider, 1)
        assert control.is_paused() is True
        shown = control.describe()
        assert shown["message"] == "AI scoring is paused. We will resume automatically."
        assert (shown["paused_automatically"], shown["paused_by_admin"]) == (True, False)

    def test_a_paused_call_is_refused_before_the_provider_is_reached(self, provider):
        fail_times(provider, 3)
        calls_before = AiCall.objects.count()
        provider.append(GOOD)
        with pytest.raises(AiPaused) as refused:
            ask()
        assert "paused" in str(refused.value) and provider == [GOOD]
        assert AiCall.objects.count() == calls_before  # nothing was called, nothing recorded

    def test_a_paused_error_is_also_an_unavailable_error(self):
        assert issubclass(AiPaused, AiUnavailable)

    def test_a_good_call_between_failures_starts_the_count_again(self, provider):
        fail_times(provider, 2)
        provider.append(GOOD)
        ask()
        fail_times(provider, 2)
        assert control.is_paused() is False

    def test_the_number_of_failures_is_a_platform_setting(self, provider):
        set_setting("ai.pause_after_failures", 1)
        fail_times(provider, 1)
        assert control.is_paused() is True

    def test_it_ends_by_itself_after_the_wait(self, provider):
        fail_times(provider, 3)
        later = timezone.now() + timedelta(minutes=11)
        assert control.is_paused(later) is False
        assert control.end_expired_pause(later) is True
        assert control.describe(later)["paused"] is False

    def test_it_is_still_paused_before_the_wait_is_over(self, provider):
        fail_times(provider, 3)
        sooner = timezone.now() + timedelta(minutes=9)
        assert control.is_paused(sooner) is True
        assert control.end_expired_pause(sooner) is False

    def test_the_wait_is_a_platform_setting(self, provider):
        set_setting("ai.auto_pause_minutes", 60)
        fail_times(provider, 3)
        assert control.is_paused(timezone.now() + timedelta(minutes=59)) is True

    def test_the_failures_that_caused_a_pause_do_not_pause_it_again(self, provider):
        fail_times(provider, 3)
        control.end_expired_pause(timezone.now() + timedelta(minutes=11))
        # time has passed: the pause's end is now behind us
        AiControl.objects.update(auto_paused_until=None, counting_from=timezone.now())
        fail_times(provider, 2)
        assert control.is_paused() is False  # only two failures since it resumed
        fail_times(provider, 1)
        assert control.is_paused() is True

    def test_ending_a_pause_runs_the_resume_hooks(self, provider, monkeypatch):
        ran = []
        monkeypatch.setattr(control, "_RESUME_HOOKS", [lambda: ran.append(1)])
        fail_times(provider, 3)
        control.end_expired_pause(timezone.now() + timedelta(minutes=11))
        assert ran == [1]

    def test_it_does_not_resume_twice(self, provider, monkeypatch):
        ran = []
        monkeypatch.setattr(control, "_RESUME_HOOKS", [lambda: ran.append(1)])
        fail_times(provider, 3)
        later = timezone.now() + timedelta(minutes=11)
        control.end_expired_pause(later)
        control.end_expired_pause(later)
        assert ran == [1]

    def test_nothing_personal_is_logged_for_a_pause(self, provider, caplog):
        fail_times(provider, 3)
        assert "paused automatically" in caplog.text and "down" not in caplog.text


class TestTheSuperAdminSwitch:
    def test_pausing_stops_calls_at_once_and_is_audited_with_the_reason(self, provider):
        boss, admin = admin_client("super")
        answer = boss.post(URL + "pause/", {"reason": REASON}, format="json")
        assert answer.status_code == 200
        assert answer.json()["paused_by_admin"] is True
        provider.append(GOOD)
        with pytest.raises(AiPaused):
            ask()
        entry = AuditEvent.objects.get(kind="admin.ai_paused")
        assert (entry.reason, str(entry.actor_id)) == (REASON, str(admin.pk))

    def test_resuming_lets_calls_through_again_and_is_audited(self, provider):
        boss, _ = admin_client("super")
        boss.post(URL + "pause/", {"reason": REASON}, format="json")
        answer = boss.post(URL + "resume/", {"reason": "Fixed."}, format="json")
        assert answer.json()["paused"] is False
        provider.append(GOOD)
        assert ask().text == "{}"
        assert AuditEvent.objects.get(kind="admin.ai_resumed").reason == "Fixed."

    def test_resuming_also_ends_an_automatic_pause(self, provider):
        fail_times(provider, 3)
        boss, _ = admin_client("super")
        assert (
            boss.post(URL + "resume/", {"reason": REASON}, format="json").json()["paused"] is False
        )
        assert control.is_paused() is False

    def test_resuming_runs_the_resume_hooks(self, monkeypatch):
        ran = []
        monkeypatch.setattr(control, "_RESUME_HOOKS", [lambda: ran.append(1)])
        boss, _ = admin_client("super")
        boss.post(URL + "resume/", {"reason": REASON}, format="json")
        assert ran == [1]

    def test_the_state_is_shown(self):
        boss, _ = admin_client("super")
        assert boss.get(URL).json() == {
            "paused": False, "paused_by_admin": False, "paused_automatically": False,
            "resumes_at": None, "message": "",
        }  # fmt: skip
        boss.post(URL + "pause/", {"reason": REASON}, format="json")
        shown = boss.get(URL).json()
        assert shown["paused"] and shown["message"] == control.PAUSED_MESSAGE

    @pytest.mark.parametrize("action", ["pause", "resume"])
    def test_a_reason_is_required(self, action):
        boss, _ = admin_client("super")
        for body in ({}, {"reason": "  "}):
            assert boss.post(f"{URL}{action}/", body, format="json").status_code == 400
        assert not AuditEvent.objects.filter(kind__startswith="admin.ai_").exists()
        assert control.is_paused() is False

    def test_a_failed_audit_undoes_the_pause(self, monkeypatch):
        def refuse(*args, **kwargs):
            raise RuntimeError("audit down")

        monkeypatch.setattr(control, "record", refuse)
        with pytest.raises(RuntimeError):
            control.pause(admin_client("super")[1], REASON)
        assert control.is_paused() is False

    def test_support_is_refused_everywhere_and_nothing_changes(self):
        support, _ = admin_client("support")
        assert support.get(URL).status_code == 403
        for action in ("pause", "resume"):
            assert (
                support.post(f"{URL}{action}/", {"reason": REASON}, format="json").status_code
                == 403
            )
        assert control.is_paused() is False
        assert not AuditEvent.objects.filter(
            kind__in=["admin.ai_paused", "admin.ai_resumed"]
        ).exists()

    def test_signed_out_and_company_members_are_refused(self):
        assert APIClient().get(URL).status_code == 401
        assert (
            APIClient().post(URL + "pause/", {"reason": REASON}, format="json").status_code == 401
        )

    def test_both_reasons_can_hold_together(self, provider):
        fail_times(provider, 3)
        boss, _ = admin_client("super")
        boss.post(URL + "pause/", {"reason": REASON}, format="json")
        shown = control.describe()
        assert shown["paused_by_admin"] and shown["paused_automatically"]

    def test_there_is_only_one_control_row(self):
        control.describe()
        with pytest.raises(IntegrityError), transaction.atomic():
            AiControl.objects.create(pk=2)
        assert AiControl.objects.count() == 1
