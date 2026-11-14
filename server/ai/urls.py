from django.urls import path

from . import views

urlpatterns = [
    path("models/", views.ModelList.as_view()),
    path("models/selection/", views.ModelSelection.as_view()),
    path("models/<str:id>/", views.ModelDetail.as_view()),
    path("prompts/", views.PromptList.as_view()),
    path("prompts/current/", views.PromptCurrent.as_view()),
    path("prompts/compare/", views.PromptCompare.as_view()),
    path("prompts/move-project/", views.PromptMoveProject.as_view()),
    path("prompts/<str:kind>/<int:number>/", views.PromptDetail.as_view()),
]
