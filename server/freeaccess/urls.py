from django.urls import path

from . import views

urlpatterns = [
    path("invites/", views.InviteList.as_view()),
    path("invites/<int:id>/", views.InviteDetail.as_view()),
    path("invites/<int:id>/extend/", views.InviteExtend.as_view()),
    path("overview/", views.BetaOverview.as_view()),
    path("paid/", views.PaidList.as_view()),
    path("access/", views.AccessList.as_view()),
    path("access/revoke-all-beta/", views.AccessRevokeAllBeta.as_view()),
    path("access/<uuid:id>/", views.AccessDetail.as_view()),
    path("access/<uuid:id>/extend/", views.AccessExtend.as_view()),
]
