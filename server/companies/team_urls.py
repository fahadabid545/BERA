from django.urls import path

from . import team_views

urlpatterns = [
    path("members/", team_views.MemberList.as_view()),
    path("members/<str:id>/", team_views.MemberRemove.as_view()),
    path("transfer-ownership/", team_views.OwnershipTransfer.as_view()),
    path("invites/", team_views.InviteList.as_view()),
    path("invites/<str:id>/resend/", team_views.InviteResend.as_view()),
    path("invites/<str:id>/", team_views.InviteRevoke.as_view()),
]
