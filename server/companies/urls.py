from django.urls import path

from . import views

urlpatterns = [
    path("company/signup/", views.sign_up_company),
    path("company/signup/country/", views.suggested_country),
]
