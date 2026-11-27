from django.urls import path

from . import admin_views as views

urlpatterns = [
    path("tickets/", views.TicketList.as_view()),
    path("tickets/<uuid:id>/", views.TicketDetail.as_view()),
]
