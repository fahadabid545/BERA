from django.urls import path

from . import views

urlpatterns = [
    path("read-description/", views.ReadDescriptionFile.as_view()),
    path("<str:id>/cvs/", views.ProjectCvUpload.as_view()),
    path("<str:id>/cvs/cancel/", views.CancelUnstarted.as_view()),
    path("<str:id>/cvs/<str:cv_id>/retry/", views.RetryFailedCv.as_view()),
    path("<str:id>/processing/", views.ProjectProcessing.as_view()),
]
