from django.urls import path

from . import views

urlpatterns = [
    path("company/refresh/", views.refresh_company),
    path("admin/refresh/", views.refresh_admin),
]
