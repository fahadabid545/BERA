from django.urls import path

from . import admin_user_views, views

urlpatterns = [
    path("admin/login/", views.login_admin),
    path("admin/accept-invite/", admin_user_views.accept_admin_invite),
    path("admin/login/two-step/", views.verify_admin_code),
    path("admin/login/two-step/setup/", views.start_admin_setup),
    path("admin/login/two-step/setup/confirm/", views.confirm_admin_setup),
]
