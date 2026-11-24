from django.urls import path

from . import views

urlpatterns = [
    path("", views.DataRequestList.as_view()),
    path("<int:id>/", views.DataRequestDetail.as_view()),
]
