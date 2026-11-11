from django.urls import path

from . import views

urlpatterns = [
    path("company/login/two-step/", views.verify_login_code),
    path("company/login/two-step/setup/", views.start_login_setup),
    path("company/login/two-step/setup/confirm/", views.confirm_login_setup),
    path("company/two-step/", views.two_step_status),
    path("company/two-step/setup/", views.start_setup),
    path("company/two-step/setup/confirm/", views.confirm_setup),
    path("company/two-step/turn-off/", views.turn_off),
    path("company/two-step/company-requirement/", views.set_company_requirement),
]
