from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import model_settings as models_service
from .models import AiModel
from .serializers import AddModelSerializer, ChangeModelSerializer, SelectModelsSerializer


class ModelSettingsView(APIView):
    """Super admins only: every route checks the role, so support is refused even when the
    address is typed in."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)


class ModelList(ModelSettingsView):
    def get(self, request):
        require_action(request.user, "ai.view")
        return Response(models_service.overview())

    def post(self, request):
        require_action(request.user, "model.change")
        serializer = AddModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        model = models_service.add_model(
            self.admin(),
            name=values["name"],
            input_price=values["input_price_per_million"],
            output_price=values["output_price_per_million"],
            enabled=values["enabled"],
        )
        return Response(models_service.describe(model), status=status.HTTP_201_CREATED)


class ModelDetail(ModelSettingsView):
    def patch(self, request, id):
        require_action(request.user, "model.change")
        serializer = ChangeModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            AiModel.objects.get(pk=id)
        except (AiModel.DoesNotExist, ValueError) as error:
            raise Http404 from error
        model = models_service.change_model(
            self.admin(),
            id,
            reason=values["reason"],
            input_price=values.get("input_price_per_million"),
            output_price=values.get("output_price_per_million"),
            enabled=values.get("enabled"),
            replacement_id=values.get("replacement"),
        )
        return Response(models_service.describe(model))


class ModelSelection(ModelSettingsView):
    def put(self, request):
        require_action(request.user, "model.change")
        serializer = SelectModelsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        choice = models_service.select_models(
            self.admin(),
            reading_id=values["reading_model"],
            scoring_id=values["scoring_model"],
            reason=values["reason"],
        )
        return Response({"choice": choice})
