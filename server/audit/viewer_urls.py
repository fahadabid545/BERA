from django.urls import path

from . import viewer_views as views

urlpatterns = [
    path("", views.AuditLog.as_view()),
    path("export/", views.AuditLogExport.as_view()),
]
