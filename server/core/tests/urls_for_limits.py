"""One route for every limit, to test them."""

from django.urls import path
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.permissions import PublicAccess
from core.throttles import (
    ContactThrottle,
    DownloadThrottle,
    InviteThrottle,
    LoginThrottle,
    PasswordResetThrottle,
    SignUpThrottle,
    UploadThrottle,
    limited,
)
from signin.authentication import CompanyAuthentication

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


def public(throttle):
    @api_view(["POST"])
    @authentication_classes([])
    @permission_classes([PublicAccess])
    @throttle_classes(limited(throttle))
    def view(request):
        return Response({"ok": True})

    return view


def signed_in(*throttles):
    @api_view(["POST", "GET"])
    @authentication_classes([CompanyAuthentication])
    @throttle_classes(limited(*throttles))
    def view(request):
        return Response({"ok": True})

    return view


urlpatterns = [
    path("api/login/", public(LoginThrottle)),
    path("api/sign-up/", public(SignUpThrottle)),
    path("api/contact/", public(ContactThrottle)),
    path("api/password-reset/", public(PasswordResetThrottle)),
    path("api/invites/", signed_in(InviteThrottle)),
    path("api/uploads/", signed_in(UploadThrottle)),
    path("api/downloads/", signed_in(DownloadThrottle)),
    path("api/anything/", signed_in()),
]
