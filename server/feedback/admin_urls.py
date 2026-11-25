from django.urls import path

from . import admin_views as views

urlpatterns = [
    path("", views.FeedbackList.as_view()),
    path("<uuid:id>/", views.FeedbackDetail.as_view()),
]
