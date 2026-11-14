from django.urls import path

from . import views

urlpatterns = [
    path("models/", views.ModelList.as_view()),
    path("models/selection/", views.ModelSelection.as_view()),
    path("models/<str:id>/", views.ModelDetail.as_view()),
]
