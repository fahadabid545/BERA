from django.urls import path

from . import views

urlpatterns = [
    path("company/login/", views.login_company),
    path("company/logout/", views.logout_company),
    path("company/logout-all/", views.logout_all_company),
    path("company/refresh/", views.refresh_company),
    path("admin/logout/", views.logout_admin),
    path("admin/logout-all/", views.logout_all_admin),
    path("admin/refresh/", views.refresh_admin),
]
