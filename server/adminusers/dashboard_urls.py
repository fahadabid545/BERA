from django.urls import path

from . import dashboard_views as views

urlpatterns = [
    path("", views.AdminDashboard.as_view()),
    path("detail/", views.AdminDashboardDetail.as_view()),
    path("report/", views.AdminDashboardReport.as_view()),
]
