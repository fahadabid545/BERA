from django.urls import include, path

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/auth/", include("signin.urls")),
    path("api/auth/", include("companies.urls")),
    path("api/auth/", include("twostep.urls")),
    path("api/auth/", include("adminusers.urls")),
    path("api/company/team/", include("companies.team_urls")),
    path("api/company/activity/", include("activity.urls")),
    path("api/company/usage/", include("plans.company_urls")),
    path("api/admin/plans/", include("plans.urls")),
    path("api/admin/", include("adminusers.control_urls")),
    path("api/plans/", include("plans.public_urls")),
    path("api/company/projects/", include("projects.urls")),
]

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
