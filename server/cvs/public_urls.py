from django.urls import path

from . import public_views

urlpatterns = [path("<str:token>/", public_views.shared_report)]
