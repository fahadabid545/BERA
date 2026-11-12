from django.urls import path

from . import company_views

urlpatterns = [path("", company_views.PlanAndUsage.as_view())]
