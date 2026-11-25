from django.urls import path

from . import views

urlpatterns = [path("<str:id>/ask/", views.AskAboutProject.as_view())]
