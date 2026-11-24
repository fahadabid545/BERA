from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.response import Response

from companies.models import CompanyUser
from core.throttles import limited
from signin.authentication import CompanyAuthentication

from . import service


@api_view(["GET"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def shown(request):
    """The banners for the signed-in person. Who and which company come from the sign-in."""
    person = CompanyUser.objects.get(pk=request.user.user_id)
    return Response({"items": service.shown_to(person)})


@api_view(["POST"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def dismiss(request, id):
    person = CompanyUser.objects.get(pk=request.user.user_id)
    service.dismiss(person, id)
    return Response({})
