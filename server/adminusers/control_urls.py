from django.urls import path

from . import admin_user_views, company_views, profitability_views
from . import control_views as views

urlpatterns = [
    path("cost-versus-revenue/", profitability_views.CostVersusRevenue.as_view()),
    path("cost-versus-revenue/rate/", profitability_views.PkrRate.as_view()),
    path("companies/", company_views.CompaniesList.as_view()),
    path("companies/<str:id>/", company_views.CompanyPage.as_view()),
    path("companies/<str:id>/suspend/", views.SuspendCompany.as_view()),
    path("companies/<str:id>/unsuspend/", views.UnsuspendCompany.as_view()),
    path("companies/<str:id>/limits/<str:name>/", views.CompanyLimit.as_view()),
    path("companies/<str:id>/subscription/grant-free/", views.GrantFreeSubscription.as_view()),
    path("companies/<str:id>/subscription/end-free/", views.EndFreeSubscription.as_view()),
    path("companies/<str:id>/subscription/terminate/", views.TerminateSubscription.as_view()),
    path("company-users/<str:id>/block/", views.BlockMember.as_view()),
    path("company-users/<str:id>/unblock/", views.UnblockMember.as_view()),
    path("company-users/<str:id>/two-step/off/", views.TurnOffCompanyUserTwoStep.as_view()),
    path("admin-users/", admin_user_views.TeamList.as_view()),
    path("admin-users/invitations/", admin_user_views.InviteAdmin.as_view()),
    path("admin-users/invitations/<int:id>/resend/", admin_user_views.ResendInvite.as_view()),
    path("admin-users/invitations/<int:id>/revoke/", admin_user_views.RevokeInvite.as_view()),
    path("admin-users/<int:id>/role/", admin_user_views.ChangeRole.as_view()),
    path("admin-users/<int:id>/status/", admin_user_views.ChangeStatus.as_view()),
    path("admin-users/<str:id>/two-step/reset/", views.ResetAdminTwoStep.as_view()),
]
