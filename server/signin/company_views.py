"""The base for every view about company data, so the ownership check cannot be forgotten.

class ProjectDetail(CompanyObjectView, RetrieveAPIView):
    queryset = Project.objects.all()
    allowed_roles = {"owner"}   # leave out to allow every company role
"""

from rest_framework.generics import GenericAPIView

from core.permissions import IsSignedIn
from core.scoping import get_company_object, require_role, scope_to_company

from .authentication import CompanyAuthentication


class CompanyObjectView(GenericAPIView):
    authentication_classes = [CompanyAuthentication]
    permission_classes = [IsSignedIn]
    allowed_roles = None
    lookup_field = "id"

    def get_queryset(self):
        # Lists and searches see only the user's company, not just single records.
        queryset = scope_to_company(super().get_queryset(), self.request.user)
        require_role(self.request.user, self.allowed_roles)
        return queryset

    def get_object(self):
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        return get_company_object(
            super().get_queryset(),
            self.request.user,
            allowed_roles=self.allowed_roles,
            **{self.lookup_field: lookup_value},
        )
