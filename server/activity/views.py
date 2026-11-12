from rest_framework.response import Response

from signin.company_views import CompanyObjectView

from . import service
from .models import ActivityEntry
from .serializers import ListQuerySerializer


class ActivityList(CompanyObjectView):
    """The signed-in owner's own company only; no company id is ever taken from the request."""

    queryset = ActivityEntry.objects.all()
    required_action = "activity.view"

    def get(self, request):
        self.get_queryset()  # checks the role and the company
        query = ListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        entries, next_before = service.list_entries(
            request.user.company_id, query.validated_data.get("before")
        )
        return Response(
            {
                "entries": [
                    {
                        "id": str(entry.id),
                        "kind": entry.kind,
                        "actor_name": entry.actor_name,
                        "target_kind": entry.target_kind,
                        "target_id": entry.target_id,
                        "details": entry.details,
                        "created_at": entry.created_at,
                    }
                    for entry in entries
                ],
                "next_before": next_before,
            }
        )
