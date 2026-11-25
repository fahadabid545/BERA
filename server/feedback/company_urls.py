from django.urls import path

from . import company_views as views

urlpatterns = [path("", views.send_feedback)]
