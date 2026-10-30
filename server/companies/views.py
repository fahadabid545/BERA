from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.permissions import PublicAccess
from core.throttles import SignUpThrottle, limited

from .country_detection import detect_country
from .serializers import SignUpSerializer
from .signup import NEUTRAL_MESSAGE, sign_up


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # a visitor has no account yet
@throttle_classes(limited(SignUpThrottle))
def sign_up_company(request):
    serializer = SignUpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    values.pop("accept_terms")
    sign_up(**values)
    return Response({"status": "ok", "message": NEUTRAL_MESSAGE})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([PublicAccess])  # shown on the sign-up form before there is an account
def suggested_country(request):
    return Response({"country": detect_country(request)})
