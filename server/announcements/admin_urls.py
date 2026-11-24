from django.urls import path

from . import admin_views as views

urlpatterns = [
    path("", views.AnnouncementList.as_view()),
    path("<int:id>/", views.AnnouncementDetail.as_view()),
]
