from django.urls import path

from . import views

urlpatterns = [
    path("", views.ProjectList.as_view()),
    path("<str:id>/", views.ProjectDetail.as_view()),
    path("<str:id>/archive/", views.ProjectArchive.as_view()),
    path("<str:id>/scoring/", views.ProjectScoringSettingsView.as_view()),
    path("<str:id>/requirements/", views.ProjectRequirements.as_view()),
    path("<str:id>/requirements/suggest/", views.ProjectRequirementSuggestions.as_view()),
    path("<str:id>/restore/", views.ProjectRestore.as_view()),
]
