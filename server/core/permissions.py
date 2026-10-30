from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission


class IsSignedIn(BasePermission):
    """The default for every route. Missing, expired and invalid sign-ins get one answer."""

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        raise NotAuthenticated()


class PublicAccess(BasePermission):
    """Marks a route as open to visitors. Only for routes on `core.public_routes.PUBLIC_ROUTES`."""

    def has_permission(self, request, view):
        return True
