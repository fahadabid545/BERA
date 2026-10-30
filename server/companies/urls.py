from django.urls import path

from . import views

urlpatterns = [
    path("company/signup/", views.sign_up_company),
    path("company/signup/country/", views.suggested_country),
    path("company/forgot-password/", views.forgot_company_password),
    path("company/reset-password/", views.reset_company_password),
    path("company/verify-email/", views.verify_company_email),
    path("company/verify-email/resend/", views.resend_company_verification),
]
