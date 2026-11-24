from django.urls import path

from . import company_views as views

urlpatterns = [
    path("", views.shown),
    path("<int:id>/dismiss/", views.dismiss),
]
