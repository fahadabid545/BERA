"""The owner's own keys. Everything is limited to the signed-in owner's company."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from companies.models import CompanyUser
from companies.role_matrix import require_action
from core.permissions import IsSignedIn
from core.throttles import limited
from signin.authentication import CompanyAuthentication

from . import service
from .scopes import SCOPES
from .serializers import NewKeyInput

ACTION = "api_key.manage"


class KeyView(APIView):
    authentication_classes = [CompanyAuthentication]
    permission_classes = [IsSignedIn]

    def get_throttles(self):
        return [throttle() for throttle in limited()]

    def owner(self):
        require_action(self.request.user, ACTION)
        return CompanyUser.objects.get(pk=self.request.user.user_id)


class KeyList(KeyView):
    def get(self, request):
        owner = self.owner()
        return Response({"keys": service.list_keys(owner.company_id), "scopes": list(SCOPES)})

    def post(self, request):
        owner = self.owner()
        serializer = NewKeyInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        key, token = service.create_key(
            owner, values["name"], values["scopes"], values["expires_at"]
        )
        response = Response({**service.describe(key), "key": token}, status=status.HTTP_201_CREATED)
        response["Cache-Control"] = "no-store"  # the one time the key is shown
        return response


class KeyRevoke(KeyView):
    def post(self, request, id):
        owner = self.owner()
        return Response(service.describe(service.revoke_key(owner, id)))
