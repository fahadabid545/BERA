"""The audit log viewer: filters, paging that stays fast on a big log, and an export that is
itself logged. Super admin only."""

import csv
import io
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from audit.service import record
from core.tests.factories import make_admin_user, make_company, make_company_user
from cvs.tests.test_ai_reading import set_setting

pytestmark = pytest.mark.django_db
URL = "/api/admin/audit-log/"
EXPORT = URL + "export/"
DAY = timedelta(days=1)
BASE = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


@contextmanager
def at(moment):
    with patch("django.utils.timezone.now", return_value=moment):
        yield


def entry(kind="auth.login", moment=BASE, **fields):
    with at(moment):
        return record(kind, **fields)


@pytest.fixture
def boss():
    return admin_client("super")


def listed(reply):
    assert reply.status_code == 200, reply.json()
    return [item["id"] for item in reply.json()["items"]]


def rows_of(reply):
    body = b"".join(reply.streaming_content).decode()
    return list(csv.reader(io.StringIO(body)))


class TestWhatIsShown:
    def test_entries_come_newest_first_with_who_and_which_company(self, boss):
        company = make_company(name="Fake Findable Ltd")
        person = make_company_user(company, name="Fake Person")
        older = entry(moment=BASE, actor=person)
        newer = entry("auth.login_failed", moment=BASE + DAY, company_id=company.pk)
        reply = boss[0].get(URL)
        assert listed(reply)[:2] == [newer.pk, older.pk]
        by_id = {item["id"]: item for item in reply.json()["items"]}
        assert by_id[older.pk]["person"] == {
            "kind": "company",
            "id": person.pk,
            "name": "Fake Person",
        }
        assert by_id[older.pk]["company"] == "Fake Findable Ltd"
        assert by_id[newer.pk]["person"]["kind"] == "none"

    def test_the_reason_the_target_and_the_details_are_shown(self, boss):
        target = make_admin_user()
        entry(
            "admin.status_changed",
            actor=boss[1],
            target=target,
            reason="Fake reason.",
            details={"status_after": "blocked"},
        )
        item = next(
            i for i in boss[0].get(URL).json()["items"] if i["action"] == "admin.status_changed"
        )
        assert (item["reason"], item["target_kind"], item["details"]) == (
            "Fake reason.",
            "admin_user",
            {"status_after": "blocked"},
        )

    def test_the_actions_to_filter_by_are_offered(self, boss):
        actions = boss[0].get(URL).json()["actions"]
        assert "auth.login" in actions and actions == sorted(actions)


class TestFilters:
    def test_by_action(self, boss):
        login = entry("auth.login")
        entry("auth.login_failed")
        assert listed(boss[0].get(URL, {"action": "auth.login"})) == [login.pk]

    def test_by_company(self, boss):
        mine, other = make_company(), make_company()
        hit = entry(company_id=mine.pk)
        entry(company_id=other.pk)
        assert listed(boss[0].get(URL, {"company": mine.pk})) == [hit.pk]

    def test_by_person_name_or_email_for_admins_and_company_people(self, boss):
        admin = make_admin_user(name="Fake Zelda Admin", email="zelda-admin@example.test")
        person = make_company_user(name="Fake Zelda Member", email="zelda-member@example.test")
        other = make_company_user(name="Fake Someone Else")
        a = entry(actor=admin)
        b = entry(actor=person)
        entry(actor=other)
        assert set(listed(boss[0].get(URL, {"person": "zelda"}))) == {a.pk, b.pk}
        assert listed(boss[0].get(URL, {"person": "zelda-admin@"})) == [a.pk]

    def test_a_person_nobody_matches_gives_an_empty_list(self, boss):
        entry()
        assert listed(boss[0].get(URL, {"person": "nobody-called-this"})) == []

    def test_a_person_search_that_is_too_short_is_refused(self, boss):
        reply = boss[0].get(URL, {"person": "ab"})
        assert reply.status_code == 400 and "person" in reply.json()["error"]["fields"]

    def test_by_dates_both_ends_included(self, boss):
        before = entry(moment=BASE - DAY)
        first = entry(moment=BASE.replace(hour=0, minute=0))
        last = entry(moment=BASE.replace(hour=23, minute=59))
        after = entry(moment=BASE + DAY)
        day = BASE.date().isoformat()
        assert set(listed(boss[0].get(URL, {"from_date": day, "to_date": day}))) == {
            first.pk,
            last.pk,
        }
        assert before.pk not in listed(boss[0].get(URL, {"from_date": day}))
        assert (
            listed(boss[0].get(URL, {"to_date": (BASE - DAY).date().isoformat()}))[0] == before.pk
        )
        assert after.pk in listed(boss[0].get(URL, {"from_date": day}))

    def test_filters_combine(self, boss):
        company = make_company()
        hit = entry("auth.login", moment=BASE, company_id=company.pk)
        entry("auth.login_failed", moment=BASE, company_id=company.pk)
        entry("auth.login", moment=BASE + 5 * DAY, company_id=company.pk)
        query = {
            "company": company.pk,
            "action": "auth.login",
            "to_date": BASE.date().isoformat(),
        }
        assert listed(boss[0].get(URL, query)) == [hit.pk]

    @pytest.mark.parametrize(
        "query",
        [
            {"action": "made.up"},
            {"company": "abc"},
            {"company": 0},
            {"from_date": "not a date"},
            {"from_date": "2026-03-10", "to_date": "2026-03-01"},
            {"colour": "red"},
            {"cursor": "garbage"},
        ],
    )
    def test_a_bad_filter_is_refused(self, boss, query):
        assert boss[0].get(URL, query).status_code == 400


class TestPagingOnALargeLog:
    def test_pages_cover_every_entry_once_newest_first(self, boss):
        set_setting("audit_log.page_size", 3)
        made = [entry(moment=BASE + timedelta(minutes=n)).pk for n in range(8)]
        seen, cursor = [], None
        while True:
            reply = boss[0].get(URL, {"cursor": cursor} if cursor else {})
            seen += listed(reply)
            cursor = reply.json()["next"]
            if not cursor:
                break
        assert seen == list(reversed(made))

    def test_entries_with_the_same_time_are_not_lost_between_pages(self, boss):
        set_setting("audit_log.page_size", 2)
        made = [entry(moment=BASE).pk for _ in range(5)]
        seen, cursor = [], None
        for _ in range(5):
            reply = boss[0].get(URL, {"cursor": cursor} if cursor else {})
            seen += listed(reply)
            cursor = reply.json()["next"]
            if not cursor:
                break
        assert sorted(seen) == sorted(made) and len(seen) == len(set(seen))

    def test_the_last_page_has_no_next_marker(self, boss):
        entry()
        assert boss[0].get(URL).json()["next"] is None

    def test_a_page_never_counts_the_whole_log_and_uses_few_queries(self, boss):
        for n in range(30):
            entry(moment=BASE + timedelta(minutes=n))
        set_setting("audit_log.page_size", 10)
        with CaptureQueriesContext(connection) as queries:
            boss[0].get(URL)
        statements = [q["sql"].upper() for q in queries]
        assert not any("COUNT(" in sql for sql in statements)
        assert len(statements) <= 12  # the sign-in checks, one page, and a name lookup each

    def test_the_page_size_is_a_platform_setting(self, boss):
        set_setting("audit_log.page_size", 2)
        for _ in range(4):
            entry()
        assert len(boss[0].get(URL).json()["items"]) == 2

    def test_an_index_serves_the_newest_first_view(self):
        assert "audit_newest_first" in {index.name for index in AuditEvent._meta.indexes}


class TestExport:
    def test_it_is_a_csv_of_the_entries_that_match(self, boss):
        company = make_company(name="Fake Findable Ltd")
        entry("auth.login", company_id=company.pk, details={"how": "password"})
        entry("auth.login_failed")
        reply = boss[0].get(EXPORT, {"company": company.pk})
        assert reply.status_code == 200
        assert reply["Content-Type"].startswith("text/csv")
        assert (
            "attachment" in reply["Content-Disposition"] and ".csv" in reply["Content-Disposition"]
        )
        rows = rows_of(reply)
        assert rows[0][:3] == ["Time (UTC)", "Action", "Person type"]
        assert len(rows) == 2
        assert (rows[1][0], rows[1][1], rows[1][6]) == (
            "2026-03-10 12:00:00",
            "auth.login",
            "Fake Findable Ltd",
        )
        assert "password" in rows[1][10]

    def test_cells_that_look_like_formulas_are_quoted(self, boss):
        entry("admin.status_changed", reason='=HYPERLINK("http://example.test")')
        rows = rows_of(boss[0].get(EXPORT))
        assert rows[1][9].startswith("'=")

    def test_the_export_is_itself_recorded_with_who_filters_and_count(self, boss):
        client, me = boss
        searched = make_admin_user(name="Fake Private Searchterm")
        entry("auth.login", actor=searched)
        entry("auth.login", actor=searched)
        entry("auth.login")
        rows_of(client.get(EXPORT, {"action": "auth.login", "person": "private searchterm"}))
        event = AuditEvent.objects.get(kind="admin.audit_log_exported")
        assert (event.actor_kind, event.actor_id) == ("admin", me.pk)
        assert event.details["rows"] == 2
        assert "action=auth.login" in event.details["filters"]
        assert "searchterm" not in str(event.details).lower()
        assert "person search" in event.details["filters"]
        assert event.created_at is not None

    def test_the_export_does_not_contain_its_own_entry_but_the_next_one_does(self, boss):
        entry("auth.login")
        first = rows_of(boss[0].get(EXPORT))
        assert [row[1] for row in first[1:]] == ["auth.login"]
        second = rows_of(boss[0].get(EXPORT))
        assert "admin.audit_log_exported" in [row[1] for row in second[1:]]

    def test_an_export_of_nothing_is_just_the_header_and_still_recorded(self, boss):
        rows = rows_of(boss[0].get(EXPORT, {"action": "invite.sent"}))
        assert len(rows) == 1
        assert AuditEvent.objects.filter(kind="admin.audit_log_exported").count() == 1

    def test_too_big_an_export_is_refused_clearly_and_not_started(self, boss):
        set_setting("audit_log.export_max_rows", 3)
        for _ in range(4):
            entry()
        reply = boss[0].get(EXPORT)
        assert reply.status_code == 400
        error = reply.json()["error"]
        assert error["code"] == "audit_export_too_large"
        assert "Narrow the dates" in error["message"] and "3" in error["message"]
        assert not AuditEvent.objects.filter(kind="admin.audit_log_exported").exists()

    def test_exactly_the_limit_is_allowed(self, boss):
        set_setting("audit_log.export_max_rows", 3)
        for _ in range(3):
            entry()
        assert len(rows_of(boss[0].get(EXPORT))) == 4

    def test_it_streams_a_long_log_in_chunks(self, boss, monkeypatch):
        from audit import log_viewer

        monkeypatch.setattr(log_viewer, "EXPORT_CHUNK", 2)
        for n in range(5):
            entry(moment=BASE + timedelta(minutes=n))
        assert len(rows_of(boss[0].get(EXPORT))) == 6

    def test_bad_filters_are_refused(self, boss):
        assert boss[0].get(EXPORT, {"action": "made.up"}).status_code == 400
        assert boss[0].get(EXPORT, {"cursor": "x"}).status_code == 400


class TestSuperAdminOnly:
    def test_support_is_refused_for_reading_and_exporting(self):
        support = admin_client("support")[0]
        entry()
        assert support.get(URL).status_code == 403
        assert support.get(EXPORT).status_code == 403
        assert not AuditEvent.objects.filter(kind="admin.audit_log_exported").exists()

    def test_a_visitor_is_refused(self, client):
        assert client.get(URL).status_code == 401
        assert client.get(EXPORT).status_code == 401
