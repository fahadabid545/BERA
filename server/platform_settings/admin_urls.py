from django.urls import path

from . import views

urlpatterns = [
    path("", views.SettingsList.as_view()),
    path("maintenance/", views.Maintenance.as_view()),
    path("legal-review/", views.LegalReview.as_view()),
    path("<str:key>/reset/", views.SettingReset.as_view()),
]
