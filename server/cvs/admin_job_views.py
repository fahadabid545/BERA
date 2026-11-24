from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from adminusers.models import AdminUser
from adminusers.role_matrix import require_action
from core.validation import StrictSerializer
from signin.authentication import AdminAuthentication

from . import job_monitor


class JobListQuery(StrictSerializer):
    """The query string of the list. Unknown or invalid values are refused, not ignored."""

    state = serializers.ChoiceField(choices=job_monitor.STATES, required=False)
    company = serializers.IntegerField(min_value=1, max_value=2_000_000_000, required=False)


class JobView(APIView):
    """Both admin roles may watch and fix jobs; every route checks the role itself."""

    authentication_classes = [AdminAuthentication]

    def admin(self):
        return AdminUser.objects.get(pk=self.request.user.user_id)


class JobList(JobView):
    def get(self, request):
        require_action(request.user, "job.view")
        query = JobListQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        return Response(
            job_monitor.list_jobs(state=values.get("state"), company_id=values.get("company"))
        )


class JobRetry(JobView):
    def post(self, request, id):
        require_action(request.user, "job.retry")
        job_monitor.retry_job(self.admin(), id)
        return Response({})


class JobCancel(JobView):
    def post(self, request, id):
        require_action(request.user, "job.cancel")
        job_monitor.cancel_job(self.admin(), id)
        return Response({})
