from rest_framework.response import Response

from core.throttles import AskThrottle, limited
from signin.company_views import CandidateDataView

from . import chats
from .models import AgentChat
from .serializers import QuestionInput


class AgentView(CandidateDataView):
    """Every person of the company who may see candidates may use the agent; another company's
    chat is "not found". Admin and support staff are refused."""

    queryset = AgentChat.objects.all()
    required_action = "candidate.view"


class ChatList(AgentView):
    def get(self, request):
        self.get_queryset()  # the company and role check
        return Response({"chats": chats.list_chats(request.user)})


class ChatDetail(AgentView):
    def get(self, request, id):
        chat = self.get_object()
        return Response(
            {"id": str(chat.pk), "title": chat.title, "messages": chats.messages_of(chat)}
        )

    def delete(self, request, id):
        self.get_object().delete()
        return Response({"deleted": True})


class Ask(AgentView):
    def get_throttles(self):
        return [throttle() for throttle in limited(AskThrottle)]

    def post(self, request):
        self.get_queryset()  # the company and role check
        serializer = QuestionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent = serializer.validated_data
        reply = chats.ask(
            request.user,
            sent["question"],
            chat_id=sent["chat_id"],
            incognito=sent["incognito"],
            history=[{"role": item["role"], "text": item["text"]} for item in sent["history"]],
            shown=[str(item) for item in sent["shown"]],
        )
        response = Response(reply)
        response["Cache-Control"] = "no-store"
        return response
