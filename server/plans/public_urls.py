from django.urls import path

from . import public_views

urlpatterns = [path("", public_views.public_plans)]
