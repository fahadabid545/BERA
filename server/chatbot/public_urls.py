from django.urls import path

from . import public_views

urlpatterns = [
    path("status/", public_views.chat_status),
    path("ask/", public_views.ask_chat),
]
