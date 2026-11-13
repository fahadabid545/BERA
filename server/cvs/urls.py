from django.urls import path

from . import views

urlpatterns = [path("<str:id>/cvs/", views.ProjectCvUpload.as_view())]
