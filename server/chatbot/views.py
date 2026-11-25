from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import controls, documents
from .serializers import DocumentFileInput, SettingsInput, SwitchInput


class ChatbotView(APIView):
    """Super admins only, checked on every method: a hidden menu item is never what keeps
    support out."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)

    def values(self, serializer_class):
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def state(self):
        return {"settings": controls.describe(), "documents": documents.list_documents()}


class ChatbotOverview(ChatbotView):
    def get(self, request):
        require_action(request.user, "chatbot.view")
        return Response(self.state())

    def put(self, request):
        require_action(request.user, "chatbot.change")
        controls.update(self.admin(), self.values(SettingsInput))
        return Response(self.state())


class DocumentList(ChatbotView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        require_action(request.user, "chatbot.change")
        sent = self.values(DocumentFileInput)["file"]
        documents.add(self.admin(), name=sent.name, data=sent.read())
        return Response(self.state(), status=201)


class DocumentDetail(ChatbotView):
    def get_parsers(self):
        # Only replacing sends a file; switching on or off sends JSON.
        return [MultiPartParser()] if self.request.method == "PUT" else [JSONParser()]

    def put(self, request, id):
        require_action(request.user, "chatbot.change")
        sent = self.values(DocumentFileInput)["file"]
        documents.replace(self.admin(), id, name=sent.name, data=sent.read())
        return Response(self.state())

    def patch(self, request, id):
        require_action(request.user, "chatbot.change")
        documents.switch(self.admin(), id, enabled=self.values(SwitchInput)["enabled"])
        return Response(self.state())

    def delete(self, request, id):
        require_action(request.user, "chatbot.change")
        documents.delete(self.admin(), id)
        return Response(self.state())
