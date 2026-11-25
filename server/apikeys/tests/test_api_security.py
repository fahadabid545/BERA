"""Attacks on the API's door: every way a key can be missing, wrong, ended or unqualified."""

import logging
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apikeys.authentication import ApiKeyAuthentication
from apikeys.models import ApiKey
from apikeys.tests.helpers import API, client_with, end_subscription, make_key, make_tenant
from audit.models import AuditEvent
from companies.models import Company, CompanyUser
from core.tests.factories import make_admin_user, start_session_for
from core.tests.test_route_protection import all_routes, authenticators_of
from cvs.tests.test_ai_reading import set_setting
from plans import subscriptions as subs
from plans.models import Plan, Subscription

pytestmark = pytest.mark.django_db
NOT_SIGNED_IN = {"error": {"code": "not_signed_in", "message": "You are not signed in."}}
LIST = f"{API}projects/"


@pytest.fixture
def tenant():
    return make_tenant()


def api_routes():
    return [
        route for route, view in all_routes() if ApiKeyAuthentication in authenticators_of(view)
    ]


def address(route):
    import re

    return "/" + re.sub(r"<uuid:\w+>", "00000000-0000-0000-0000-000000000000", route)


def refused(response):
    assert response.status_code == 401
    assert response.json() == NOT_SIGNED_IN


def test_the_walk_finds_every_api_route():
    assert len(api_routes()) == 5


@pytest.mark.parametrize("route", api_routes())
class TestEveryApiRoute:
    @pytest.mark.parametrize("method", ["get", "post", "patch", "put", "delete"])
    def test_no_key_is_refused(self, route, method):
        refused(getattr(APIClient(), method)(address(route)))

    @pytest.mark.parametrize(
        "token", ["", "x", "bera_live_", "bera_live_" + "a" * 43, "a" * 5000, "null", "Bearer"]
    )
    def test_garbage_is_refused_with_the_same_answer(self, route, token):
        refused(client_with(token).get(address(route)))

    def test_a_key_in_the_address_or_a_cookie_is_ignored(self, tenant, route):
        _, token = make_key(tenant)
        client = APIClient()
        client.cookies["access"] = token
        refused(client.get(address(route), {"key": token, "api_key": token}))


class TestWrongKeys:
    def test_a_changed_key_is_refused(self, tenant):
        _, token = make_key(tenant)
        flipped = token[:-1] + ("A" if token[-1] != "A" else "B")
        refused(client_with(flipped).get(LIST))

    def test_a_company_sign_in_token_is_not_a_key(self, tenant):
        issued = start_session_for(
            user_id=tenant.owner.pk, role="owner", company_id=tenant.company.pk, kind="company"
        )
        refused(client_with(issued.access_token).get(LIST))

    def test_an_admin_sign_in_token_is_not_a_key(self):
        admin = make_admin_user()
        issued = start_session_for(user_id=admin.pk, role="super", company_id=None, kind="admin")
        refused(client_with(issued.access_token).get(LIST))

    def test_a_key_does_not_open_company_or_admin_routes(self, tenant):
        _, token = make_key(tenant)
        api = client_with(token)
        for route in (
            "/api/company/projects/",
            "/api/company/team/members/",
            "/api/company/billing/change-plan/",
            f"/api/company/projects/{tenant.project.pk}/candidates/",
            "/api/admin/feedback/",
            "/api/admin/settings/",
        ):
            assert api.get(route).status_code == 401, route

    def test_expired_and_revoked_keys_get_the_same_answer_as_unknown_ones(self, tenant):
        key, token = make_key(tenant, expires_at=timezone.now() + timedelta(days=1))
        ApiKey.objects.filter(pk=key.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        refused(client_with(token).get(LIST))
        ApiKey.objects.filter(pk=key.pk).update(expires_at=None, revoked_at=timezone.now())
        refused(client_with(token).get(LIST))

    def test_a_key_works_until_the_moment_it_expires(self, tenant):
        _, token = make_key(tenant, expires_at=timezone.now() + timedelta(days=1))
        assert client_with(token).get(LIST).status_code == 200


class TestWhoStillQualifies:
    def test_a_suspended_company_stops_at_once(self, tenant):
        _, token = make_key(tenant)
        api = client_with(token)
        assert api.get(LIST).status_code == 200
        Company.objects.filter(pk=tenant.company.pk).update(status="suspended")
        reply = api.get(LIST)
        assert (reply.status_code, reply.json()["error"]["code"]) == (403, "api_access_closed")

    def test_a_company_waiting_to_be_deleted_stops(self, tenant):
        _, token = make_key(tenant)
        Company.objects.filter(pk=tenant.company.pk).update(status="pending_deletion")
        assert client_with(token).get(LIST).status_code == 403

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_a_key_stops_when_the_person_who_made_it_is_blocked_or_removed(self, tenant, status):
        _, token = make_key(tenant)
        CompanyUser.objects.filter(pk=tenant.owner.pk).update(status=status)
        assert client_with(token).get(LIST).status_code == 403

    @pytest.mark.parametrize("state", ["expired", "no_plan", "past_due"])
    def test_a_subscription_that_is_not_active_paid_or_granted_stops_the_key(self, tenant, state):
        _, token = make_key(tenant)
        end_subscription(tenant.company)
        Subscription.objects.filter(company_id=tenant.company.pk).update(
            state=state,
            period_end=timezone.now() + timedelta(days=5),
            past_due_since=timezone.now(),
        )
        reply = client_with(token).get(LIST)
        assert (reply.status_code, reply.json()["error"]["code"]) == (403, "api_access_closed")

    def test_a_cancelled_subscription_works_until_its_paid_period_ends(self, tenant):
        _, token = make_key(tenant)
        subs.cancel(tenant.company.pk, by=None) if False else None
        Subscription.objects.filter(company_id=tenant.company.pk).update(state="cancelled")
        assert client_with(token).get(LIST).status_code == 200
        Subscription.objects.filter(company_id=tenant.company.pk).update(
            period_end=timezone.now() - timedelta(days=1)
        )
        assert client_with(token).get(LIST).status_code == 403

    def test_a_free_grant_counts(self, tenant):
        _, token = make_key(tenant)
        Subscription.objects.filter(company_id=tenant.company.pk).update(state="granted_free")
        assert client_with(token).get(LIST).status_code == 200

    def test_the_subscription_does_not_need_a_plan_with_a_price(self, tenant):
        _, token = make_key(tenant)
        Plan.objects.update(price_usd=0)
        assert client_with(token).get(LIST).status_code == 200


class TestRecordsAndLimits:
    def test_a_refused_key_is_recorded_without_the_key(self, tenant):
        _, token = make_key(tenant)
        wrong = token[:-1] + ("A" if token[-1] != "A" else "B")
        client_with(wrong).get(LIST)
        event = AuditEvent.objects.get(kind="security.api_key_refused")
        assert event.details == {"why": "unknown"}
        assert wrong not in str(event.__dict__) and token not in str(event.__dict__)

    def test_a_revoked_keys_use_is_recorded_for_its_company(self, tenant):
        key, token = make_key(tenant)
        ApiKey.objects.filter(pk=key.pk).update(revoked_at=timezone.now())
        client_with(token).get(LIST)
        event = AuditEvent.objects.get(kind="security.api_key_refused")
        assert (event.company_id, event.details["why"]) == (tenant.company.pk, "revoked")

    def test_wrong_keys_from_one_address_are_limited(self, tenant):
        set_setting("rate_limits.api_key_failures_per_minute", 3)
        answers = [client_with("bera_live_" + "x" * 43).get(LIST).status_code for _ in range(5)]
        assert answers == [401, 401, 401, 429, 429]
        assert AuditEvent.objects.filter(kind="security.api_key_refused").count() == 3

    def test_other_addresses_are_not_limited_by_one_attacker(self, tenant):
        set_setting("rate_limits.api_key_failures_per_minute", 1)
        for _ in range(3):
            APIClient(REMOTE_ADDR="203.0.113.7", HTTP_AUTHORIZATION="Bearer bera_live_zz").get(LIST)
        _, token = make_key(tenant)
        assert (
            APIClient(REMOTE_ADDR="203.0.113.8", HTTP_AUTHORIZATION=f"Bearer {token}")
            .get(LIST)
            .status_code
            == 200
        )

    def test_good_keys_are_not_counted_as_failures(self, tenant):
        set_setting("rate_limits.api_key_failures_per_minute", 1)
        _, token = make_key(tenant)
        assert all(client_with(token).get(LIST).status_code == 200 for _ in range(4))

    def test_the_key_and_the_request_body_are_never_logged(self, tenant, caplog):
        _, token = make_key(tenant)
        with caplog.at_level(logging.DEBUG):
            client_with(token).get(LIST)
            client_with(token + "x").get(LIST)
            client_with(token).post(
                f"{API}projects/{tenant.project.pk}/cvs/", {"batch": "SECRET-BODY"}, format="json"
            )
        assert token not in caplog.text and "SECRET-BODY" not in caplog.text
