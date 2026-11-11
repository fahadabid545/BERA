from django.urls import include, path

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/auth/", include("signin.urls")),
    path("api/auth/", include("companies.urls")),
    path("api/auth/", include("twostep.urls")),
]

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
