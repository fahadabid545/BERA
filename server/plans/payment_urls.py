from django.urls import path

from . import payment_views

urlpatterns = [path("", payment_views.PaymentList.as_view())]
