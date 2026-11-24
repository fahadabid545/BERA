from django.urls import path

from . import admin_job_views as views

urlpatterns = [
    path("", views.JobList.as_view()),
    path("<str:id>/retry/", views.JobRetry.as_view()),
    path("<str:id>/cancel/", views.JobCancel.as_view()),
]
