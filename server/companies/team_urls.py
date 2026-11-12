from django.urls import path

from . import team_views

urlpatterns = [
    path("invites/", team_views.InviteList.as_view()),
    path("invites/<str:id>/resend/", team_views.InviteResend.as_view()),
    path("invites/<str:id>/", team_views.InviteRevoke.as_view()),
]
