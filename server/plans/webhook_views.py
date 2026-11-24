import stripe
from django.conf import settings
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.errors import AppError
from core.permissions import PublicAccess

from .stripe_events import handle_event

INVALID_CODE = "invalid_signature"
INVALID_MESSAGE = "The notification could not be verified."


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the provider has no account; the signature is the credential
@throttle_classes(
    []
)  # a burst of genuine notifications must not be refused; forged ones fail below
def stripe_webhook(request):
    """Only a notification signed with our shared secret (and not older than the provider's
    tolerance) is read at all. Everything else is refused before the body is looked at."""
    try:
        event = stripe.Webhook.construct_event(
            request.body,
            request.headers.get("Stripe-Signature", ""),
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.SignatureVerificationError) as error:
        raise AppError(INVALID_CODE, INVALID_MESSAGE, status_code=400) from error
    return Response({"received": True, "outcome": handle_event(event.to_dict())})
