from django.urls import path

from . import views

urlpatterns = [
    path("chats/", views.ChatList.as_view()),
    path("chats/<str:id>/", views.ChatDetail.as_view()),
    path("ask/", views.Ask.as_view()),
]
