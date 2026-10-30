import pytest
from django.urls import URLPattern, URLResolver, get_resolver, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from core.permissions import IsSignedIn, PublicAccess
from core.public_routes import PUBLIC_CATEGORIES, PUBLIC_ROUTES
from signin.authentication import KindAuthentication


def all_routes(patterns=None, prefix=""):
    """Every (route, view function) the server answers, found by walking the URL tree."""
    for pattern in patterns if patterns is not None else get_resolver().url_patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from all_routes(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern):
            yield route, pattern.callback


PUBLIC_ROUTE_NAMES = {entry.route for entry in PUBLIC_ROUTES}


def permissions_of(view):
    return list(getattr(getattr(view, "cls", None), "permission_classes", []))


def authenticators_of(view):
    return list(getattr(getattr(view, "cls", None), "authentication_classes", []))


def unprotected(routes):
    """Routes that are neither correctly public (on the list) nor protected."""
    found = []
    for route, view in routes:
        permissions = permissions_of(view)
        if route in PUBLIC_ROUTE_NAMES:
            ok = PublicAccess in permissions
        else:
            # A private route must also say which kind of user it is for (company or admin).
            ok = (
                any(issubclass(p, IsSignedIn) for p in permissions)
                and not any(issubclass(p, (PublicAccess, AllowAny)) for p in permissions)
                and any(issubclass(a, KindAuthentication) for a in authenticators_of(view))
            )
        if not ok:
            found.append(route)
    return found


def test_every_route_is_either_public_on_the_list_or_protected():
    assert unprotected(all_routes()) == []


def test_the_public_list_only_names_routes_that_exist():
    existing = {route for route, _ in all_routes()}
    assert PUBLIC_ROUTE_NAMES <= existing


@pytest.mark.parametrize("entry", PUBLIC_ROUTES, ids=lambda entry: entry.route)
def test_each_public_route_has_an_allowed_category_and_a_reason(entry):
    assert entry.category in PUBLIC_CATEGORIES
    assert entry.reason.strip()


def test_the_check_catches_open_routes_missing_from_the_list():
    @api_view(["GET"])
    @permission_classes([AllowAny])
    def forgotten(request): ...

    def plain_django_view(request): ...

    @api_view(["GET"])
    def signed_in_but_for_nobody(request): ...

    routes = all_routes(
        [
            path("api/forgotten/", forgotten),
            path("plain/", plain_django_view),
            path("api/nobody/", signed_in_but_for_nobody),
        ]
    )
    assert unprotected(routes) == ["api/forgotten/", "plain/", "api/nobody/"]


def test_the_default_for_a_new_view_is_to_require_sign_in():
    @api_view(["GET"])
    def new_view(request): ...

    assert any(issubclass(p, IsSignedIn) for p in permissions_of(new_view))


def test_health_check_is_open_to_visitors(db):
    assert APIClient().get("/api/health/").status_code == 200
