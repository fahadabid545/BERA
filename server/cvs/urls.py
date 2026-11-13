from django.urls import path

from . import views

urlpatterns = [
    path("read-description/", views.ReadDescriptionFile.as_view()),
    path("<str:id>/cvs/", views.ProjectCvUpload.as_view()),
]
