from django.urls import path

from . import control_views as views

urlpatterns = [
    path("companies/<str:id>/suspend/", views.SuspendCompany.as_view()),
    path("companies/<str:id>/unsuspend/", views.UnsuspendCompany.as_view()),
    path("companies/<str:id>/limits/<str:name>/", views.CompanyLimit.as_view()),
    path("companies/<str:id>/subscription/grant-free/", views.GrantFreeSubscription.as_view()),
    path("companies/<str:id>/subscription/end-free/", views.EndFreeSubscription.as_view()),
    path("companies/<str:id>/subscription/terminate/", views.TerminateSubscription.as_view()),
    path("company-users/<str:id>/block/", views.BlockMember.as_view()),
    path("company-users/<str:id>/unblock/", views.UnblockMember.as_view()),
    path("company-users/<str:id>/two-step/off/", views.TurnOffCompanyUserTwoStep.as_view()),
    path("admin-users/<str:id>/two-step/reset/", views.ResetAdminTwoStep.as_view()),
]
