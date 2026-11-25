"""The owner's keys: made, shown once, stored only hashed, listed, revoked."""

import hashlib
import logging
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apikeys import keys
from apikeys.models import ApiKey
from apikeys.tests.helpers import API, KEYS, client_with, end_subscription, make_key, make_tenant
from audit.models import AuditEvent
from companies.deletion import remove_company
from companies.tests.test_role_matrix import client_for
from core.tests.factories import make_company_user
from cvs.tests.test_ai_reading import set_setting
from signin.tests.models_for_tests import KINDS_OF_OBJECT

pytestmark = pytest.mark.django_db
ALL = ["projects:read", "cvs:upload", "candidates:read"]


@pytest.fixture
def tenant():
    return make_tenant()


def create(tenant, **over):
    body = {"name": "Fake key", "scopes": ALL, **over}
    return tenant.client.post(KEYS, body, format="json")


class TestCreating:
    def test_the_key_is_shown_once_with_a_fixed_start(self, tenant):
        reply = create(tenant)
        assert reply.status_code == 201
        body = reply.json()
        assert body["key"].startswith("bera_live_") and len(body["key"]) > 40
        assert reply["Cache-Control"] == "no-store"
        listed = tenant.client.get(KEYS).json()["keys"]
        assert "key" not in listed[0]
        assert listed[0]["last_four"] == body["key"][-4:]

    def test_only_the_hash_is_stored(self, tenant):
        token = create(tenant).json()["key"]
        stored = ApiKey.objects.get()
        assert stored.key_hash == hashlib.sha256(token.encode()).hexdigest()
        with connection.cursor() as cursor:
            cursor.execute("select * from apikeys_apikey")
            row = " ".join(str(value) for value in cursor.fetchone())
        assert token not in row

    def test_two_keys_are_never_the_same(self, tenant):
        assert create(tenant).json()["key"] != create(tenant).json()["key"]

    def test_the_scopes_are_kept_sorted_and_cannot_be_changed_later(self, tenant):
        key_id = create(tenant, scopes=["projects:read", "candidates:read"]).json()["id"]
        assert ApiKey.objects.get(pk=key_id).scopes == ["candidates:read", "projects:read"]
        assert tenant.client.patch(
            f"{KEYS}{key_id}/", {"scopes": ALL}, format="json"
        ).status_code in (
            404,
            405,
        )

    @pytest.mark.parametrize(
        "over",
        [
            {"scopes": []},
            {"scopes": ["projects:read", "projects:read"]},
            {"scopes": ["candidates:delete"]},
            {"scopes": ["contacts:read"]},
            {"scopes": "projects:read"},
            {"name": ""},
            {"name": "x" * 101},
            {"expires_at": "2020-01-01T00:00:00Z"},
            {"expires_at": "soon"},
            {"extra": 1},
        ],
    )
    def test_a_bad_request_is_refused(self, tenant, over):
        assert create(tenant, **over).status_code == 400
        assert not ApiKey.objects.exists()

    def test_an_expiry_in_the_future_is_kept(self, tenant):
        when = (timezone.now() + timedelta(days=5)).isoformat()
        assert create(tenant, expires_at=when).json()["expires_at"] is not None

    def test_a_company_has_a_limited_number_of_active_keys(self, tenant):
        set_setting("api.max_active_keys_per_company", 2)
        create(tenant)
        first = create(tenant).json()["id"]
        refused = create(tenant)
        assert (refused.status_code, refused.json()["error"]["code"]) == (409, "too_many_api_keys")
        tenant.client.post(f"{KEYS}{first}/revoke/")
        assert create(tenant).status_code == 201

    def test_it_is_audited_without_the_key(self, tenant):
        token = create(tenant).json()["key"]
        event = AuditEvent.objects.get(kind="api_key.created")
        assert event.actor_id == tenant.owner.pk and event.company_id == tenant.company.pk
        assert event.details["scopes"] == ",".join(sorted(ALL))
        assert token not in str(event.__dict__)

    def test_a_company_without_a_qualifying_subscription_cannot_make_one(self, tenant):
        end_subscription(tenant.company)
        reply = create(tenant)
        assert (reply.status_code, reply.json()["error"]["code"]) == (403, "api_access_closed")


class TestWhoMayManageKeys:
    def test_a_member_may_not_list_make_or_revoke(self, tenant):
        key, _ = make_key(tenant)
        member = client_for(make_company_user(tenant.company, role="member"))
        assert member.get(KEYS).status_code == 403
        assert member.post(KEYS, {"name": "x", "scopes": ALL}, format="json").status_code == 403
        assert member.post(f"{KEYS}{key.pk}/revoke/").status_code == 403
        key.refresh_from_db()
        assert key.revoked_at is None

    def test_nobody_signed_in_is_refused(self, tenant):
        from rest_framework.test import APIClient

        assert APIClient().get(KEYS).status_code == 401

    def test_an_api_key_cannot_manage_keys(self, tenant):
        _, token = make_key(tenant)
        assert client_with(token).get(KEYS).status_code == 401
        assert client_with(token).post(KEYS, {}, format="json").status_code == 401


class TestListing:
    def test_it_lists_the_companys_keys_with_usage_and_never_another_companys(self, tenant):
        make_key(tenant, name="Mine")
        other = make_tenant()
        make_key(other, name="Theirs")
        listed = tenant.client.get(KEYS).json()["keys"]
        assert [each["name"] for each in listed] == ["Mine"]
        assert listed[0]["request_count"] == 0 and listed[0]["last_used_at"] is None

    def test_using_a_key_counts_and_dates_the_use(self, tenant):
        key, token = make_key(tenant)
        client_with(token).get(f"{API}projects/")
        client_with(token).get(f"{API}projects/")
        key.refresh_from_db()
        assert key.request_count == 2 and key.last_used_at is not None


class TestRevoking:
    def test_a_revoked_key_stops_at_once(self, tenant):
        key, token = make_key(tenant)
        api = client_with(token)
        assert api.get(f"{API}projects/").status_code == 200
        assert tenant.client.post(f"{KEYS}{key.pk}/revoke/").status_code == 200
        assert api.get(f"{API}projects/").status_code == 401

    def test_revoking_twice_changes_nothing_and_is_audited_once(self, tenant):
        key, _ = make_key(tenant)
        tenant.client.post(f"{KEYS}{key.pk}/revoke/")
        first = ApiKey.objects.get(pk=key.pk).revoked_at
        assert tenant.client.post(f"{KEYS}{key.pk}/revoke/").status_code == 200
        assert ApiKey.objects.get(pk=key.pk).revoked_at == first
        assert AuditEvent.objects.filter(kind="api_key.revoked").count() == 1

    def test_another_companys_key_is_not_found_and_stays_live(self, tenant):
        other = make_tenant()
        key, token = make_key(other)
        assert tenant.client.post(f"{KEYS}{key.pk}/revoke/").status_code == 404
        assert client_with(token).get(f"{API}projects/").status_code == 200

    def test_the_key_text_is_not_logged(self, tenant, caplog):
        with caplog.at_level(logging.DEBUG):
            token = create(tenant).json()["key"]
            client_with(token).get(f"{API}projects/")
        assert token not in caplog.text

    def test_the_prefix_and_hash_helpers(self):
        token = keys.new_token()
        assert token.startswith(keys.PREFIX)
        assert keys.hash_of(token) == hashlib.sha256(token.encode()).hexdigest()


class TestCompanyDeletion:
    @pytest.fixture(autouse=True)
    def stand_in_tables(self, db):
        """Deleting a company looks at every model that points at it, including the stand-ins the
        isolation tests register for the whole run, so their tables must exist here too."""
        with connection.schema_editor() as editor:
            for model in KINDS_OF_OBJECT.values():
                editor.create_model(model)

    def test_deleting_a_company_removes_its_keys_and_only_its_keys(self):
        gone, kept = make_tenant(), make_tenant()
        make_key(gone)
        make_key(kept)
        remove_company(gone.company.pk)
        assert list(ApiKey.objects.values_list("company_id", flat=True)) == [kept.company.pk]
