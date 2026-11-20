from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from adminusers.models import AdminUser
from ai import spend_alerts
from ai.models import AiCall, AiSpendAlert
from ai.tests.test_model_settings import REASON, admin_client
from audit.models import AuditEvent
from core.tests.factories import make_admin_user, make_company
from cvs import processing
from cvs.tests.test_ai_reading import set_setting
from emailing.models import OutgoingEmail
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache, get_setting

pytestmark = pytest.mark.django_db
URL = "/api/admin/ai/controls/spend-alerts/"
NOON = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def spend(amount, when=NOON, result="ok"):
    call = AiCall.objects.create(
        company=make_company(), purpose="scoring", model="fake-model", duration_ms=1,
        result=result, estimated_cost=Decimal(amount),
    )  # fmt: skip
    AiCall.objects.filter(pk=call.pk).update(created_at=when)


def alerts_sent():
    return OutgoingEmail.objects.filter(template="ai_spend_alert")


@pytest.fixture(autouse=True)
def two_super_admins():
    make_admin_user(email="first@example.test")
    make_admin_user(email="second@example.test")


class TestOneAlertPerCrossing:
    def test_no_limit_means_no_alert(self):
        spend("1000")
        assert spend_alerts.check(NOON) == []
        assert alerts_sent().count() == 0

    def test_spending_under_the_limit_sends_nothing(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("49.99")
        assert spend_alerts.check(NOON) == []
        assert alerts_sent().count() == 0

    def test_crossing_the_daily_limit_sends_one_alert_to_each_super_admin(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("30")
        spend("25")
        assert spend_alerts.check(NOON) == ["daily"]
        assert sorted(alerts_sent().values_list("to_address", flat=True)) == [
            "first@example.test",
            "second@example.test",
        ]
        email = alerts_sent().first()
        assert "55.00" in email.text_body and "50.00" in email.text_body

    def test_the_limit_itself_counts_as_crossed(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("50")
        assert spend_alerts.check(NOON) == ["daily"]

    def test_checking_again_in_the_same_day_sends_nothing(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("60")
        spend_alerts.check(NOON)
        spend("10")
        assert spend_alerts.check(NOON + timedelta(minutes=5)) == []
        assert alerts_sent().count() == 2  # the two super admins, once
        assert AiSpendAlert.objects.count() == 1

    def test_the_next_day_is_a_new_crossing(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("60")
        spend_alerts.check(NOON)
        tomorrow = NOON + timedelta(days=1)
        assert spend_alerts.check(tomorrow) == []  # nothing spent yet today
        spend("60", when=tomorrow)
        assert spend_alerts.check(tomorrow) == ["daily"]
        assert AiSpendAlert.objects.count() == 2

    def test_raising_the_limit_and_crossing_it_again_is_a_new_crossing(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("60")
        spend_alerts.check(NOON)
        set_setting("ai.daily_spend_alert_usd", 100)
        assert spend_alerts.check(NOON) == []
        spend("45")
        assert spend_alerts.check(NOON) == ["daily"]

    def test_a_stored_alert_stops_a_second_check_even_if_both_run_at_once(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("60")
        AiSpendAlert.objects.create(
            kind="daily", period="2026-11-20", limit_usd=Decimal("50"), spent_usd=Decimal("60")
        )
        assert spend_alerts.check(NOON) == []
        assert alerts_sent().count() == 0


class TestMonthlyAndPeriods:
    def test_the_monthly_limit_counts_the_whole_month_and_the_daily_only_today(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        set_setting("ai.monthly_spend_alert_usd", 100)
        spend("40", when=NOON - timedelta(days=3))
        spend("40", when=NOON - timedelta(days=2))
        spend("30", when=NOON)
        assert spend_alerts.check(NOON) == ["monthly"]

    def test_both_limits_crossed_at_once_alert_twice_one_each(self):
        set_setting("ai.daily_spend_alert_usd", 10)
        set_setting("ai.monthly_spend_alert_usd", 20)
        spend("25")
        assert spend_alerts.check(NOON) == ["daily", "monthly"]
        assert AiSpendAlert.objects.count() == 2

    def test_spending_in_the_last_month_does_not_count(self):
        set_setting("ai.monthly_spend_alert_usd", 100)
        spend("500", when=datetime(2026, 10, 31, 23, 59, tzinfo=UTC))
        assert spend_alerts.check(NOON) == []

    def test_midnight_utc_starts_a_new_day(self):
        set_setting("ai.daily_spend_alert_usd", 50)
        spend("60", when=datetime(2026, 11, 19, 23, 59, tzinfo=UTC))
        assert spend_alerts.check(datetime(2026, 11, 20, 0, 1, tzinfo=UTC)) == []

    def test_failed_calls_cost_nothing(self):
        set_setting("ai.daily_spend_alert_usd", 1)
        spend("0", result="failed")
        assert spend_alerts.check(NOON) == []


class TestWhoIsEmailed:
    def test_only_active_super_admins(self):
        make_admin_user(email="support@example.test", role=AdminUser.Role.SUPPORT)
        make_admin_user(email="blocked@example.test", status=AdminUser.Status.BLOCKED)
        make_admin_user(email="removed@example.test", status=AdminUser.Status.REMOVED)
        set_setting("ai.daily_spend_alert_usd", 5)
        spend("9")
        spend_alerts.check(NOON)
        assert sorted(alerts_sent().values_list("to_address", flat=True)) == [
            "first@example.test",
            "second@example.test",
        ]

    def test_no_super_admin_still_records_the_crossing(self):
        AdminUser.objects.all().delete()
        set_setting("ai.daily_spend_alert_usd", 5)
        spend("9")
        assert spend_alerts.check(NOON) == ["daily"]
        assert alerts_sent().count() == 0

    def test_the_email_links_to_ai_controls(self):
        set_setting("ai.daily_spend_alert_usd", 5)
        spend("9")
        spend_alerts.check(NOON)
        assert "/admin/advanced/ai-controls" in alerts_sent().first().text_body


class TestTheMinuteSweep:
    def test_the_sweep_runs_the_check(self):
        set_setting("ai.daily_spend_alert_usd", 5)
        spend("9", when=datetime.now(UTC))
        processing.sweep()
        processing.sweep()
        assert AiSpendAlert.objects.count() == 1
        assert alerts_sent().count() == 2


class TestSettingTheLimits:
    def body(self, **changes):
        return {"daily_limit": "50.00", "monthly_limit": "900", "reason": REASON, **changes}

    def test_a_super_admin_sets_the_limits_and_it_is_audited(self):
        boss, admin = admin_client()
        answer = boss.put(URL, self.body(), format="json")
        assert answer.status_code == 200
        assert answer.json()["daily_limit"] == "50.0" and answer.json()["monthly_limit"] == "900.0"
        assert get_setting("ai.daily_spend_alert_usd") == 50
        event = AuditEvent.objects.get(kind="admin.ai_spend_alerts_changed")
        assert event.reason == REASON
        assert event.details["changes"]["daily_limit"] == {"old": None, "new": "50.00"}

    def test_null_clears_a_limit(self):
        boss, _ = admin_client()
        boss.put(URL, self.body(), format="json")
        boss.put(URL, self.body(daily_limit=None), format="json")
        assert not PlatformSetting.objects.filter(key="ai.daily_spend_alert_usd").exists()
        clear_cache()
        assert get_setting("ai.daily_spend_alert_usd") is None
        assert get_setting("ai.monthly_spend_alert_usd") == 900

    @pytest.mark.parametrize("bad", ["0", "-5", "abc", "1.234", "99999999999"])
    def test_bad_limits_are_refused(self, bad):
        boss, _ = admin_client()
        answer = boss.put(URL, self.body(daily_limit=bad), format="json")
        assert answer.status_code == 400
        assert "daily_limit" in answer.json()["error"]["fields"]

    def test_a_reason_is_required(self):
        boss, _ = admin_client()
        body = self.body()
        del body["reason"]
        assert boss.put(URL, body, format="json").status_code == 400

    def test_support_cannot_see_or_change_the_limits(self):
        helper, _ = admin_client("support")
        assert helper.get(URL).status_code == 403
        assert helper.put(URL, self.body(), format="json").status_code == 403

    def test_a_visitor_is_refused(self):
        from rest_framework.test import APIClient

        assert APIClient().get(URL).status_code == 401

    def test_the_limits_and_current_spending_are_shown(self):
        boss, _ = admin_client()
        boss.put(URL, self.body(), format="json")
        spend("12.5", when=datetime.now(UTC))
        shown = boss.get(URL).json()
        assert shown["daily_limit"] == "50.0"
        assert shown["spent_today"] == "12.50" and shown["spent_this_month"] == "12.50"
