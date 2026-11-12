from django.urls import path

from . import team_views, views

urlpatterns = [
    path("company/signup/", views.sign_up_company),
    path("company/signup/country/", views.suggested_country),
    path("company/forgot-password/", views.forgot_company_password),
    path("company/reset-password/", views.reset_company_password),
    path("company/accept-invite/", team_views.accept_company_invite),
    path("company/verify-email/", views.verify_company_email),
    path("company/verify-email/resend/", views.resend_company_verification),
]
