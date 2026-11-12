from django.urls import path

from . import views

urlpatterns = [
    path("admin/login/", views.login_admin),
    path("admin/login/two-step/", views.verify_admin_code),
    path("admin/login/two-step/setup/", views.start_admin_setup),
    path("admin/login/two-step/setup/confirm/", views.confirm_admin_setup),
]
