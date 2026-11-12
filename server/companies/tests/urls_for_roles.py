"""One stand-in route per action of the role matrix, to test what each role may do."""

from django.urls import path
from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.response import Response

from companies.role_matrix import ROLES_ALLOWED, require_action
from core.throttles import limited
from signin.authentication import CompanyAuthentication

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


def route_for(action):
    @api_view(["POST"])
    @authentication_classes([CompanyAuthentication])
    @throttle_classes(limited())
    def do_it(request):
        require_action(request.user, action)
        return Response({"done": action})

    do_it.__name__ = action.replace(".", "_")
    return path(f"api/actions/{action}/", do_it)


urlpatterns = [route_for(action) for action in ROLES_ALLOWED]
