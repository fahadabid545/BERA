from django.urls import path

from . import views

urlpatterns = [path("", views.CompanyCandidates.as_view())]
