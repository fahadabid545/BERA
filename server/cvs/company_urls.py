from django.urls import path

from . import views

urlpatterns = [path("", views.CompanyCharts.as_view())]
