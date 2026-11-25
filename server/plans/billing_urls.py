from django.urls import path

from . import checkout_views, invoice_views, renewal_views

urlpatterns = [
    path("checkout/", checkout_views.CheckoutView.as_view()),
    path("checkout/confirm/", checkout_views.CheckoutConfirmView.as_view()),
    path("change-plan/", checkout_views.ChangePlanView.as_view()),
    path("change-plan/cancel/", checkout_views.CancelDowngradeView.as_view()),
    path("cancel/", renewal_views.CancelRenewalView.as_view()),
    path("resume/", renewal_views.ResumeRenewalView.as_view()),
    path("portal/", renewal_views.BillingPortalView.as_view()),
    path("details/", invoice_views.BillingDetailsView.as_view()),
    path("invoices/", invoice_views.InvoiceListView.as_view()),
    path("invoices/<uuid:id>/link/", invoice_views.InvoiceLinkView.as_view()),
]
