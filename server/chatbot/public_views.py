from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from core.permissions import PublicAccess
from core.throttles import ChatbotThrottle, limited

from . import public_chat
from .public_serializers import VisitorQuestion


@api_view(["GET"])
@authentication_classes([])
@permission_classes([PublicAccess])  # the widget is on public pages
@throttle_classes(limited())
def chat_status(request):
    """Whether the chat is on, so the widget can hide itself when it is not, and the limits the
    browser keeps to."""
    response = Response(public_chat.widget_settings())
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
@authentication_classes([])
@permission_classes([PublicAccess])  # a visitor has no account
@throttle_classes(limited(ChatbotThrottle))
def ask_chat(request):
    serializer = VisitorQuestion(data=request.data)
    serializer.is_valid(raise_exception=True)
    reply = public_chat.answer(
        serializer.validated_data["question"], serializer.validated_data["history"]
    )
    response = Response(reply)
    response["Cache-Control"] = "no-store"
    return response
