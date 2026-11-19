from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.response import Response

from companies.models import CompanyUser
from core.throttles import limited
from signin.authentication import CompanyAuthentication

from .serializers import ChoiceSerializer
from .service import choices_of, set_choice


@api_view(["GET", "PATCH"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited())
def own_choices(request):
    """The signed-in person's own email choices; no id is ever taken from the request."""
    person = CompanyUser.objects.get(pk=request.user.user_id)
    if request.method == "GET":
        return Response({"choices": choices_of(person)})
    serializer = ChoiceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    return Response({"choices": set_choice(person, values["kind"], values["enabled"])})
