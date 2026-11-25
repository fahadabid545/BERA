from django.urls import path

from . import company_views as views

urlpatterns = [
    path("", views.KeyList.as_view()),
    path("<uuid:id>/revoke/", views.KeyRevoke.as_view()),
]
