from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from adminusers import profitability
from ai.tests.test_model_settings import admin_client
from core.errors import AppError
from core.tests.factories import make_company, make_company_user
from cvs.tests.test_ai_reading import set_setting
from plans.models import PaymentEvent
from plans.payments import record_event
from signin import service

pytestmark = pytest.mark.django_db
URL = "/api/admin/payments/"
JAN = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
FEB = datetime(2026, 2, 10, 12, 0, tzinfo=UTC)


def record(company, event_id, kind="payment", amount=1000, currency="USD", at=JAN, **extra):
    return record_event(
        provider_event_id=event_id,
        company_id=company.pk,
        kind=kind,
        amount_minor=amount,
        currency=currency,
        occurred_at=at,
        **extra,
    )


@pytest.fixture
def boss():
    return admin_client("super")[0]


@pytest.fixture
def two_companies():
    return make_company(), make_company()


def ids(reply):
    return [item["provider_event_id"] for item in reply.json()["items"]]


class TestRecordingAnEvent:
    def test_an_event_is_stored_as_the_provider_reported_it(self):
        company = make_company()
        event, created = record(company, "evt_1", amount=1250, currency="usd")
        assert created is True
        event.refresh_from_db()
        assert (event.provider_event_id, event.kind, event.amount_minor) == (
            "evt_1",
            "payment",
            1250,
        )
        assert (event.currency, event.company_id, event.occurred_at) == ("USD", company.pk, JAN)

    def test_the_same_event_delivered_twice_is_one_record(self):
        company = make_company()
        first, _ = record(company, "evt_1")
        again, created = record(company, "evt_1")
        assert created is False and again.pk == first.pk
        assert PaymentEvent.objects.count() == 1

    def test_the_same_event_id_with_other_details_is_refused_and_the_record_kept(self):
        company = make_company()
        record(company, "evt_1", amount=1000)
        for change in ({"amount": 999}, {"kind": "refund"}, {"currency": "PKR"}, {"at": FEB}):
            with pytest.raises(AppError) as refused:
                record(company, "evt_1", **change)
            assert refused.value.code == "payment_event_conflict"
        with pytest.raises(AppError):
            record(make_company(), "evt_1")
        assert PaymentEvent.objects.get().amount_minor == 1000

    def test_the_database_itself_keeps_provider_event_ids_unique(self):
        company = make_company()
        record(company, "evt_1")
        with pytest.raises(IntegrityError), transaction.atomic():
            PaymentEvent.objects.create(
                company=company, provider_event_id="evt_1", kind="payment", amount_minor=1,
                currency="USD", occurred_at=JAN,
            )  # fmt: skip

    def test_a_failure_keeps_its_reason(self):
        event, _ = record(make_company(), "evt_f", kind="failure", reason="Card declined")
        assert event.reason == "Card declined"

    @pytest.mark.parametrize(
        "change",
        [
            {"event_id": "  "},
            {"kind": "chargeback"},
            {"amount": -1},
            {"amount": 10.5},
            {"currency": "US"},
            {"currency": "US1"},
            {"currency": ""},
        ],
    )
    def test_something_that_cannot_be_a_payment_is_refused(self, change):
        company = make_company()
        arguments = {"event_id": "evt_x", **change}
        with pytest.raises(AppError) as refused:
            record(company, arguments.pop("event_id"), **arguments)
        assert refused.value.code == "payment_event_invalid"
        assert PaymentEvent.objects.count() == 0

    def test_an_unknown_company_is_refused(self):
        with pytest.raises(AppError) as refused:
            record_event(
                provider_event_id="evt_x", company_id=999_999, kind="payment", amount_minor=1,
                currency="USD", occurred_at=JAN,
            )  # fmt: skip
        assert refused.value.code == "payment_event_invalid"
        assert PaymentEvent.objects.count() == 0

    def test_a_zero_amount_is_allowed(self):
        assert record(make_company(), "evt_0", amount=0)[1] is True


class TestTheOverview:
    def test_lists_newest_first_with_the_company_and_amount(self, boss, two_companies):
        first, second = two_companies
        record(first, "evt_old", at=JAN, amount=1250)
        record(second, "evt_new", kind="refund", amount=500, at=FEB)
        shown = boss.get(URL).json()
        assert [item["provider_event_id"] for item in shown["items"]] == ["evt_new", "evt_old"]
        top = shown["items"][0]
        assert (top["kind"], top["amount"], top["currency"]) == ("refund", "5.00", "USD")
        assert (top["company_id"], top["company"]) == (second.pk, second.name)
        assert top["at"].startswith("2026-02-10")
        assert shown["items"][1]["amount"] == "12.50"

    def test_failures_show_their_reason(self, boss):
        record(make_company(), "evt_f", kind="failure", reason="Card declined")
        assert boss.get(URL).json()["items"][0]["reason"] == "Card declined"

    def test_filters_by_kind(self, boss, two_companies):
        company = two_companies[0]
        (
            record(company, "p"),
            record(company, "r", kind="refund"),
            record(company, "f", kind="failure"),
        )
        for kind, expected in (("payment", ["p"]), ("refund", ["r"]), ("failure", ["f"])):
            assert ids(boss.get(URL, {"kind": kind})) == expected

    def test_filters_by_company(self, boss, two_companies):
        first, second = two_companies
        record(first, "a"), record(second, "b")
        assert ids(boss.get(URL, {"company": second.pk})) == ["b"]

    def test_filters_by_currency(self, boss):
        company = make_company()
        record(company, "usd"), record(company, "pkr", currency="PKR")
        assert ids(boss.get(URL, {"currency": "PKR"})) == ["pkr"]

    def test_filters_by_dates_and_the_last_day_counts_whole(self, boss):
        company = make_company()
        record(company, "jan", at=JAN)
        record(company, "late", at=datetime(2026, 1, 31, 23, 59, tzinfo=UTC))
        record(company, "feb", at=FEB)
        assert ids(boss.get(URL, {"from_date": "2026-02-01"})) == ["feb"]
        assert ids(boss.get(URL, {"to_date": "2026-01-31"})) == ["late", "jan"]
        assert ids(boss.get(URL, {"from_date": "2026-01-10", "to_date": "2026-01-10"})) == ["jan"]

    def test_filters_combine(self, boss, two_companies):
        first, second = two_companies
        record(first, "a", kind="refund"), record(first, "b"), record(second, "c", kind="refund")
        assert ids(boss.get(URL, {"kind": "refund", "company": first.pk})) == ["a"]

    def test_filters_that_make_no_sense_are_refused(self, boss):
        for bad in (
            {"kind": "chargeback"}, {"company": "abc"}, {"currency": "usd"}, {"currency": "US"},
            {"from_date": "yesterday"}, {"page": 0}, {"unknown": "1"},
        ):  # fmt: skip
            assert boss.get(URL, bad).status_code == 400, bad

    def test_dates_the_wrong_way_round_are_refused(self, boss):
        reply = boss.get(URL, {"from_date": "2026-03-01", "to_date": "2026-02-01"})
        assert reply.status_code == 400 and "to_date" in reply.json()["error"]["fields"]

    def test_pages_come_from_the_platform_setting(self, boss):
        set_setting("admin_payments.page_size", 10)
        company = make_company()
        for number in range(12):
            record(company, f"evt_{number:02d}", at=datetime(2026, 1, number + 1, tzinfo=UTC))
        first = boss.get(URL).json()
        second = boss.get(URL, {"page": 2}).json()
        assert (first["total"], len(first["items"]), len(second["items"])) == (12, 10, 2)
        assert first["page_size"] == 10 and first["items"][0]["provider_event_id"] == "evt_11"
        assert boss.get(URL, {"page": 3}).json()["items"] == []

    def test_totals_are_per_currency_and_follow_the_filters(self, boss, two_companies):
        first, second = two_companies
        record(first, "p1", amount=1000), record(first, "p2", amount=250)
        record(first, "r1", kind="refund", amount=300)
        record(first, "f1", kind="failure", amount=999)
        record(second, "k1", amount=70000, currency="PKR")
        totals = {entry["currency"]: entry for entry in boss.get(URL).json()["totals"]}
        assert totals["USD"]["payments"] == {"count": 2, "amount": "12.50"}
        assert totals["USD"]["refunds"] == {"count": 1, "amount": "3.00"}
        assert totals["USD"]["failures"] == {"count": 1}
        assert totals["PKR"]["payments"] == {"count": 1, "amount": "700.00"}
        only = boss.get(URL, {"company": second.pk}).json()["totals"]
        assert [entry["currency"] for entry in only] == ["PKR"]

    def test_offers_only_companies_and_currencies_that_have_records(self, boss, two_companies):
        first, second = two_companies
        make_company()
        record(first, "a"), record(second, "b", currency="PKR")
        shown = boss.get(URL).json()
        assert sorted(item["id"] for item in shown["companies"]) == sorted([first.pk, second.pk])
        assert shown["currencies"] == ["PKR", "USD"]

    def test_with_no_records_it_is_empty(self, boss):
        shown = boss.get(URL).json()
        assert (shown["total"], shown["items"], shown["totals"]) == (0, [], [])

    def test_the_numbers_are_the_records_exactly(self, boss):
        """Every provider event is one row, whatever order and however many times it arrived."""
        company = make_company()
        for event_id in ("e1", "e2", "e1", "e3", "e2", "e1"):
            record(company, event_id)
        assert sorted(ids(boss.get(URL))) == ["e1", "e2", "e3"]
        assert boss.get(URL).json()["total"] == PaymentEvent.objects.count() == 3


class TestOnlySuperAdmins:
    def test_support_is_refused(self, two_companies):
        record(two_companies[0], "evt_1")
        reply = admin_client("support")[0].get(URL)
        assert reply.status_code == 403
        assert "1000" not in reply.content.decode() and "10.00" not in reply.content.decode()

    def test_a_company_user_is_refused(self, two_companies):
        person = make_company_user(two_companies[0])
        issued = service.start_session(
            user_id=person.pk, role="owner", company_id=person.company_id, kind="company"
        )
        member = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert member.get(URL).status_code in (401, 403)

    def test_someone_not_signed_in_is_refused(self):
        assert APIClient().get(URL).status_code == 401


def test_cost_versus_revenue_still_uses_the_estimate(boss):
    """Real payments replace the estimated revenue in a later ticket; records change nothing."""
    company = make_company()
    before = boss.get("/api/admin/cost-versus-revenue/").json()
    record(company, "evt_1", amount=999_900)
    assert boss.get("/api/admin/cost-versus-revenue/").json() == before
    assert profitability.amount_paid  # the one function real payments will replace


def test_amounts_are_shown_with_two_decimals():
    from plans.payment_overview import money

    assert [money(0), money(5), money(100), money(123_456)] == ["0.00", "0.05", "1.00", "1234.56"]
    assert Decimal(money(123_456)) == Decimal("1234.56")


class TestAnotherCompany:
    """Payment records belong to a company but no company route reads them: a company user is
    refused the admin list, even filtered to their own company, and the list shows each record
    under its own company only."""

    def test_a_company_user_cannot_read_even_their_own_companys_records(self, two_companies):
        mine, theirs = two_companies
        record(mine, "mine"), record(theirs, "theirs")
        person = make_company_user(mine)
        issued = service.start_session(
            user_id=person.pk, role="owner", company_id=mine.pk, kind="company"
        )
        member = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        for query in ({}, {"company": mine.pk}, {"company": theirs.pk}):
            reply = member.get(URL, query)
            assert reply.status_code in (401, 403)
            assert "theirs" not in reply.content.decode() and "mine" not in reply.content.decode()

    def test_each_record_is_listed_under_its_own_company(self, boss, two_companies):
        mine, theirs = two_companies
        record(mine, "mine"), record(theirs, "theirs")
        for company, event_id in ((mine, "mine"), (theirs, "theirs")):
            shown = boss.get(URL, {"company": company.pk}).json()["items"]
            assert [(item["provider_event_id"], item["company_id"]) for item in shown] == [
                (event_id, company.pk)
            ]
