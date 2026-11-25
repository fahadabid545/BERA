from django.urls import path

from . import views

urlpatterns = [
    path("", views.ChatbotOverview.as_view()),
    path("documents/", views.DocumentList.as_view()),
    path("documents/<int:id>/", views.DocumentDetail.as_view()),
]
