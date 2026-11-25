from django.urls import path

from . import api_views as views

urlpatterns = [
    path("projects/", views.ProjectList.as_view()),
    path("projects/<uuid:id>/", views.ProjectDetail.as_view()),
    path("projects/<uuid:id>/cvs/", views.CvUpload.as_view()),
    path("projects/<uuid:id>/candidates/", views.Candidates.as_view()),
    path("projects/<uuid:id>/candidates/<uuid:candidate_id>/", views.CandidateDetail.as_view()),
]
