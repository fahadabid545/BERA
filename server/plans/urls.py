from django.urls import path

from . import views

urlpatterns = [
    path("", views.PlanList.as_view()),
    path("<str:id>/", views.PlanDetail.as_view()),
]
