from django.urls import path

from . import account_views

urlpatterns = [
    path("profile/", account_views.own_profile),
    path("profile/email/", account_views.own_email_change),
    path("settings/", account_views.company_settings_view),
]
