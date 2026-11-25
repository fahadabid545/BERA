from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.response import Response

from companies.models import CompanyUser
from core.throttles import FeedbackThrottle, limited
from signin.authentication import CompanyAuthentication

from . import service
from .serializers import NewFeedbackInput


@api_view(["POST"])
@authentication_classes([CompanyAuthentication])
@throttle_classes(limited(FeedbackThrottle))
def send_feedback(request):
    """Every signed-in person of a company may send feedback. Who and which company come from
    the sign-in, never from the request."""
    serializer = NewFeedbackInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    person = CompanyUser.objects.get(pk=request.user.user_id)
    service.send(person, serializer.validated_data)
    return Response({}, status=201)
