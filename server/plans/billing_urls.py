from django.urls import path

from . import checkout_views

urlpatterns = [
    path("checkout/", checkout_views.CheckoutView.as_view()),
    path("checkout/confirm/", checkout_views.CheckoutConfirmView.as_view()),
    path("change-plan/", checkout_views.ChangePlanView.as_view()),
    path("change-plan/cancel/", checkout_views.CancelDowngradeView.as_view()),
]
