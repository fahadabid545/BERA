from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.permissions import PublicAccess
from core.throttles import ContactThrottle, limited

from . import form_token, service
from .serializers import ContactInput

THANK_YOU = "Thank you. Your message was sent."


@api_view(["GET"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the form is on a public page
@throttle_classes(limited())
def contact_form(request):
    """What the form needs: the privacy notice and the signed moment it was opened."""
    response = Response(
        {
            "privacy_note": service.privacy_note(),
            "form_token": form_token.issue(),
            # A form left open is given a fresh token before the old one expires, so a message
            # written slowly is never mistaken for spam.
            "refresh_after_seconds": form_token.refresh_after_seconds(),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # a visitor has no account
@throttle_classes(limited(ContactThrottle))
def send_contact_message(request):
    serializer = ContactInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    service.receive(serializer.validated_data)
    return Response({"message": THANK_YOU})
