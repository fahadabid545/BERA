from rest_framework.response import Response

from core.throttles import SupportThrottle, limited
from signin.company_views import CompanyObjectView

from . import chats, tickets
from .models import SupportTicket
from .serializers import ChatMessageInput, TicketReplyInput


class SupportView(CompanyObjectView):
    """Every person of a company may use support; admin and support staff are refused.
    Another person's chat, and a ticket the person may not read, are "not found"."""

    queryset = SupportTicket.objects.all()
    allowed_roles = ("owner", "member")

    def check(self):
        self.get_queryset()  # the company and role check


class ChatMessage(SupportView):
    def get_throttles(self):
        return [throttle() for throttle in limited(SupportThrottle)]

    def post(self, request):
        self.check()
        serializer = ChatMessageInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent = serializer.validated_data
        response = Response(chats.send(request.user, sent["text"], sent["chat_id"]))
        response["Cache-Control"] = "no-store"
        return response


class ChatDetail(SupportView):
    def get(self, request, id):
        self.check()
        chat = chats.get_chat(request.user, id)
        return Response({"id": str(chat.pk), "messages": chats.messages_of(chat)})


class TicketList(SupportView):
    def get(self, request):
        self.check()
        return Response({"tickets": tickets.list_for(request.user)})


class TicketDetail(SupportView):
    def get(self, request, id):
        self.check()
        return Response(tickets.detail_of(tickets.get_for(request.user, id)))

    def post(self, request, id):
        """The person answers the team."""
        self.check()
        serializer = TicketReplyInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = tickets.person_replies(request.user, id, serializer.validated_data["text"])
        return Response(tickets.detail_of(ticket))
