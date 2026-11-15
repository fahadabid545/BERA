from django.urls import path

from . import views

urlpatterns = [
    path("", views.CompanyDashboard.as_view()),
    path("detail/", views.CompanyDashboardDetail.as_view()),
    path("report/", views.CompanyDashboardReport.as_view()),
]
