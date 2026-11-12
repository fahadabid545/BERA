from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from plans.models import Plan
from plans.pricing import PKR_MISSING_NOTE, price_for
from plans.service import active_plans

URL = "/api/plans/"
THROUGH_PROXY = {"HTTP_X_FORWARDED_FOR": "198.51.100.7"}
pytestmark = pytest.mark.django_db

LIMITS = {
    "cvs_per_month": 100,
    "cvs_per_project": 50,
    "max_projects": 5,
    "max_team_accounts": 3,
    "max_top_n": 10,
    "monthly_ai_token_cap": 1_000_000,
}


def make_plan(name="Fake Plan", *, status="active", usd="10.00", pkr="3000.00", order=0):
    return Plan.objects.create(
        name=name,
        status=status,
        price_usd=Decimal(usd),
        price_pkr=None if pkr is None else Decimal(pkr),
        display_order=order,
        **LIMITS,
    )


def visitor_sees(country_header=None):
    extra = dict(THROUGH_PROXY)
    if country_header is not None:
        extra["HTTP_CF_IPCOUNTRY"] = country_header
    with override_settings(APP_ENV="production", TRUSTED_PROXY_COUNT=1):
        response = APIClient(REMOTE_ADDR="10.0.0.2").get(URL, **extra)
    assert response.status_code == 200
    return response.json()


class TestPriceFor:
    def test_pakistan_sees_the_pkr_price(self):
        price = price_for(make_plan(), "PK")
        assert (price.currency, price.amount, price.note) == ("PKR", Decimal("3000.00"), None)

    @pytest.mark.parametrize("country", ["pk", " PK ", "Pk"])
    def test_pakistan_is_found_whatever_the_spelling(self, country):
        assert price_for(make_plan(), country).currency == "PKR"

    @pytest.mark.parametrize("country", ["US", "DE", "IN", "AE"])
    def test_other_countries_see_usd_without_a_note(self, country):
        price = price_for(make_plan(), country)
        assert (price.currency, price.amount, price.note) == ("USD", Decimal("10.00"), None)

    @pytest.mark.parametrize("country", ["ZZ", "", None, "XX", "Pakistan", "12"])
    def test_an_unknown_country_falls_back_to_usd(self, country):
        price = price_for(make_plan(), country)
        assert (price.currency, price.note) == ("USD", None)

    def test_pakistan_without_a_pkr_price_sees_usd_with_a_note(self):
        price = price_for(make_plan(pkr=None), "PK")
        assert (price.currency, price.amount, price.note) == (
            "USD",
            Decimal("10.00"),
            PKR_MISSING_NOTE,
        )

    def test_a_missing_pkr_price_gives_no_note_elsewhere(self):
        assert price_for(make_plan(pkr=None), "US").note is None


class TestThePublicList:
    def test_works_without_signing_in(self):
        make_plan()
        assert len(visitor_sees("US")) == 1

    def test_only_active_plans_are_listed(self):
        make_plan("Shown")
        make_plan("Hidden", status="hidden")
        make_plan("Archived", status="archived")
        assert [plan["name"] for plan in visitor_sees("US")] == ["Shown"]
        assert [plan.name for plan in active_plans()] == ["Shown"]

    def test_the_starting_plans_are_not_public_until_active(self):
        assert visitor_sees("PK") == []

    def test_plans_follow_the_display_order(self):
        make_plan("Second", order=2)
        make_plan("First", order=1)
        assert [plan["name"] for plan in visitor_sees()] == ["First", "Second"]

    def test_a_visitor_in_pakistan_sees_pkr(self):
        make_plan()
        price = visitor_sees("PK")[0]["price"]
        assert price == {"currency": "PKR", "amount": "3000.00", "note": None}

    def test_a_visitor_elsewhere_sees_usd(self):
        make_plan()
        price = visitor_sees("DE")[0]["price"]
        assert price == {"currency": "USD", "amount": "10.00", "note": None}

    def test_an_unknown_country_sees_usd(self):
        make_plan()
        assert visitor_sees("XX")[0]["price"]["currency"] == "USD"
        assert visitor_sees()[0]["price"]["currency"] == "USD"

    def test_a_missing_pkr_price_shows_usd_with_a_note_in_pakistan(self):
        make_plan(pkr=None)
        price = visitor_sees("PK")[0]["price"]
        assert (price["currency"], price["amount"], price["note"]) == (
            "USD",
            "10.00",
            PKR_MISSING_NOTE,
        )

    def test_a_country_header_written_by_the_visitor_is_not_believed(self):
        make_plan()
        with override_settings(APP_ENV="production", TRUSTED_PROXY_COUNT=1):
            response = APIClient(REMOTE_ADDR="10.0.0.2").get(URL, HTTP_CF_IPCOUNTRY="PK")
        assert response.json()[0]["price"]["currency"] == "USD"

    def test_no_internal_fields_are_shown(self):
        make_plan()
        shown = set(visitor_sees("US")[0])
        assert shown.isdisjoint({"status", "subscribers", "pending_change", "monthly_ai_token_cap"})

    def test_only_reading_is_allowed(self):
        for method in ("post", "patch", "delete"):
            assert getattr(APIClient(), method)(URL).status_code == 405


class TestTheCompanyCountryIsLocked:
    def test_sign_up_is_the_only_place_that_accepts_a_country(self):
        from companies import serializers

        accepting = {
            name
            for name, value in vars(serializers).items()
            if isinstance(value, type)
            and issubclass(value, serializers.serializers.Serializer)
            and "country" in value().fields
        }
        assert accepting == {"SignUpSerializer"}
