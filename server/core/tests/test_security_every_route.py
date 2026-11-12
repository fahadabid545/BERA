"""Attacks every protected route of the server, so a new route is covered the day it is added.

The routes are found by walking the real URL tree (like test_route_protection). Each one must
refuse: no sign-in, a tampered or unsigned token, an expired token, a token for the other kind
of sign-in, a refresh token used as an access token, a session that ended, a blocked person
and a suspended company. All with the same answer, which reveals nothing.
"""

import base64
import json

import pytest
from rest_framework.test import APIClient

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from core.tests.factories import make_admin_user, make_company, make_company_user
from core.tests.test_route_protection import PUBLIC_ROUTE_NAMES, all_routes, authenticators_of
from signin import service
from signin.authentication import AdminAuthentication, CompanyAuthentication
from signin.models import Session
from signin.service import RevokeReason
from signin.tests.helpers import forge

pytestmark = pytest.mark.django_db
NOT_SIGNED_IN = {"error": {"code": "not_signed_in", "message": "You are not signed in."}}
METHODS = ("get", "post", "put", "patch", "delete")


def protected_routes():
    """(route, method, kind) for every private route and every method it answers."""
    found = []
    for route, view in all_routes():
        if route in PUBLIC_ROUTE_NAMES:
            continue
        kinds = {
            "company" if issubclass(a, CompanyAuthentication) else "admin"
            for a in authenticators_of(view)
            if issubclass(a, (CompanyAuthentication, AdminAuthentication))
        }
        assert len(kinds) == 1, f"{route} must be for exactly one kind of sign-in"
        methods = [m for m in METHODS if m in getattr(view.cls, "http_method_names", [])]
        methods = [m for m in methods if hasattr(view.cls, m)]
        found += [(route, method, next(iter(kinds))) for method in methods]
    return found


ROUTES = protected_routes()
IDS = [f"{method.upper()} {route} ({kind})" for route, method, kind in ROUTES]
OTHER = {"company": "admin", "admin": "company"}


def address(route):
    return "/" + route.replace("<str:id>", "x").replace("<int:pk>", "1")


def sign_in(kind):
    if kind == "company":
        person = make_company_user(make_company(), role="owner", email_verified=True)
        issued = service.start_session(
            user_id=person.pk, role="owner", company_id=person.company_id, kind="company"
        )
    else:
        person = make_admin_user()
        issued = service.start_session(
            user_id=person.pk, role="super", company_id=None, kind="admin"
        )
    return person, issued


def call(token, route, method):
    client = APIClient(HTTP_AUTHORIZATION=f"Bearer {token}") if token else APIClient()
    return getattr(client, method)(address(route), {}, format="json")


def refused(response):
    assert response.status_code == 401
    assert response.json() == NOT_SIGNED_IN


def encode_part(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()


def claims_of(token):
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))


def test_the_walk_finds_the_protected_routes():
    assert len(ROUTES) >= 8, "the walk should find every private route of the server"
    assert {kind for _, _, kind in ROUTES} >= {"company"}


@pytest.mark.parametrize(("route", "method", "kind"), ROUTES, ids=IDS)
class TestEveryProtectedRoute:
    def test_a_valid_sign_in_gets_past_the_door(self, route, method, kind):
        # Anything but "not signed in": the door is open for the right person.
        _, issued = sign_in(kind)
        response = call(issued.access_token, route, method)
        assert response.status_code != 401, response.content

    def test_no_sign_in_is_refused(self, route, method, kind):
        refused(call(None, route, method))

    @pytest.mark.parametrize("garbage", ["", "not.a.token", "a" * 5000, "Bearer", "null"])
    def test_garbage_is_refused(self, route, method, kind, garbage):
        refused(call(garbage, route, method))

    def test_a_token_with_changed_claims_is_refused(self, route, method, kind):
        person, issued = sign_in(kind)
        header, payload, signature = issued.access_token.split(".")
        claims = claims_of(issued.access_token)
        claims["role"] = "super" if kind == "admin" else "owner"
        claims["sub"] = str(person.pk + 1)
        refused(call(f"{header}.{encode_part(claims)}.{signature}", route, method))

    def test_a_token_with_a_damaged_signature_is_refused(self, route, method, kind):
        _, issued = sign_in(kind)
        token = issued.access_token
        refused(
            call(token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB"), route, method)
        )

    def test_an_unsigned_token_is_refused(self, route, method, kind):
        _, issued = sign_in(kind)
        header = encode_part({"alg": "none", "typ": "JWT"})
        refused(call(f"{header}.{encode_part(claims_of(issued.access_token))}.", route, method))

    def test_an_expired_token_is_refused(self, route, method, kind):
        person, issued = sign_in(kind)
        token = forge(
            kind,
            issued_ago=3600,
            lifetime=900,
            sub=str(person.pk),
            sid=issued.session_id,
            role="owner" if kind == "company" else "super",
            cid=person.company_id if kind == "company" else None,
        )
        refused(call(token, route, method))

    def test_the_other_kinds_sign_in_is_refused(self, route, method, kind):
        _, issued = sign_in(OTHER[kind])
        refused(call(issued.access_token, route, method))

    def test_a_token_claiming_the_wrong_audience_is_refused(self, route, method, kind):
        person, issued = sign_in(kind)
        claims = claims_of(issued.access_token)
        wrong = forge(kind, **{**claims, "aud": f"bera-{OTHER[kind]}", "iat": None, "exp": None})
        refused(call(wrong, route, method))

    def test_a_refresh_token_is_not_an_access_token(self, route, method, kind):
        _, issued = sign_in(kind)
        refused(call(issued.refresh_token, route, method))

    def test_an_ended_session_is_refused(self, route, method, kind):
        person, issued = sign_in(kind)
        service.revoke_session(issued.session_id, RevokeReason.LOGOUT)
        refused(call(issued.access_token, route, method))

    def test_a_session_that_does_not_exist_is_refused(self, route, method, kind):
        _, issued = sign_in(kind)
        Session.objects.all().delete()
        refused(call(issued.access_token, route, method))

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_a_blocked_or_removed_person_is_refused_at_once(self, route, method, kind, status):
        person, issued = sign_in(kind)
        model = CompanyUser if kind == "company" else AdminUser
        model.objects.filter(pk=person.pk).update(status=status)
        refused(call(issued.access_token, route, method))


COMPANY_ROUTES = [entry for entry in ROUTES if entry[2] == "company"]


@pytest.mark.parametrize(
    ("route", "method", "kind"),
    COMPANY_ROUTES,
    ids=[f"{method.upper()} {route}" for route, method, _ in COMPANY_ROUTES],
)
def test_a_suspended_company_is_refused_at_once_on_every_company_route(route, method, kind):
    person, issued = sign_in(kind)
    Company.objects.filter(pk=person.company_id).update(status="suspended")
    refused(call(issued.access_token, route, method))
