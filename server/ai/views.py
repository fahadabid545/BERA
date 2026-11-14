from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from signin.authentication import AdminAuthentication

from . import model_settings as models_service
from . import prompt_versions
from .models import AiModel
from .serializers import (
    AddModelSerializer,
    ChangeModelSerializer,
    CompareSerializer,
    CreatePromptSerializer,
    DeletePromptSerializer,
    MakeCurrentSerializer,
    MoveProjectSerializer,
    SelectModelsSerializer,
)


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


class PromptList(ModelSettingsView):
    def get(self, request):
        require_action(request.user, "ai.view")
        return Response(prompt_versions.overview())

    def post(self, request):
        require_action(request.user, "prompt.change")
        serializer = CreatePromptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        version = prompt_versions.create_version(
            self.admin(), kind=values["kind"], text=values["text"]
        )
        return Response(prompt_versions.describe(version), status=status.HTTP_201_CREATED)


class PromptCurrent(ModelSettingsView):
    def put(self, request):
        require_action(request.user, "prompt.change")
        serializer = MakeCurrentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        version = prompt_versions.make_current(
            self.admin(), kind=values["kind"], number=values["number"], reason=values["reason"]
        )
        return Response(prompt_versions.describe(version, with_text=False))


class PromptCompare(ModelSettingsView):
    def get(self, request):
        require_action(request.user, "ai.view")
        serializer = CompareSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        return Response(prompt_versions.compare(values["kind"], values["left"], values["right"]))


class PromptMoveProject(ModelSettingsView):
    def post(self, request):
        require_action(request.user, "prompt.change")
        serializer = MoveProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        project = prompt_versions.move_project(
            self.admin(),
            project_id=values["project_id"],
            kind=values["kind"],
            number=values["number"],
            reason=values["reason"],
        )
        return Response(
            {
                "reading_prompt_version": project.reading_prompt_version,
                "scoring_prompt_version": project.scoring_prompt_version,
            }
        )


class PromptDetail(ModelSettingsView):
    def delete(self, request, kind, number):
        require_action(request.user, "prompt.change")
        if kind not in prompt_versions.KINDS:
            raise Http404
        serializer = DeletePromptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prompt_versions.delete_version(
            self.admin(), kind=kind, number=number, reason=serializer.validated_data["reason"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
