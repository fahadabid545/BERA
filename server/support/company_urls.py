from django.urls import path

from . import company_views as views

urlpatterns = [
    path("chat/", views.ChatMessage.as_view()),
    path("chat/<uuid:id>/", views.ChatDetail.as_view()),
    path("tickets/", views.TicketList.as_view()),
    path("tickets/<uuid:id>/", views.TicketDetail.as_view()),
]
