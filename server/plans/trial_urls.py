from django.urls import path

from . import trial_views

urlpatterns = [
    path("codes/", trial_views.TrialCodeList.as_view()),
    path("codes/<int:id>/", trial_views.TrialCodeDetail.as_view()),
]
