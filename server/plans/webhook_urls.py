from django.urls import path

from . import webhook_views

urlpatterns = [path("stripe/webhook/", webhook_views.stripe_webhook)]
