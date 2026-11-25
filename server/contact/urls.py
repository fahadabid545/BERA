from django.urls import path

from . import views

urlpatterns = [
    path("", views.send_contact_message),
    path("form/", views.contact_form),
]
