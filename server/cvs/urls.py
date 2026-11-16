from django.urls import path

from . import views

urlpatterns = [
    path("read-description/", views.ReadDescriptionFile.as_view()),
    path("<str:id>/cvs/", views.ProjectCvUpload.as_view()),
    path("<str:id>/cvs/estimate/", views.CostEstimate.as_view()),
    path("<str:id>/cvs/cancel/", views.CancelUnstarted.as_view()),
    path("<str:id>/cvs/<str:cv_id>/retry/", views.RetryFailedCv.as_view()),
    path("<str:id>/candidates/", views.ProjectCandidates.as_view()),
    path("<str:id>/reports/", views.ProjectReports.as_view()),
    path("<str:id>/reports/<str:report_id>/revoke/", views.ProjectReportRevoke.as_view()),
    path("<str:id>/charts/", views.ProjectCharts.as_view()),
    path("<str:id>/compare/", views.CandidateComparison.as_view()),
    path("<str:id>/matrix/", views.CandidateMatrix.as_view()),
    path("<str:id>/frontier/", views.ProjectFrontier.as_view()),
    path("<str:id>/downloads/", views.ProjectDownloads.as_view()),
    path("<str:id>/candidates/export/", views.ProjectListExport.as_view()),
    path("<str:id>/candidates/stage/", views.CandidateStages.as_view()),
    path("<str:id>/candidates/<str:candidate_id>/", views.CandidateDetail.as_view()),
    path("<str:id>/candidates/<str:candidate_id>/notes/", views.CandidateNotes.as_view()),
    path(
        "<str:id>/candidates/<str:candidate_id>/notes/<str:note_id>/",
        views.CandidateNoteItem.as_view(),
    ),
    path("<str:id>/candidates/<str:candidate_id>/cv/", views.CandidateCvFile.as_view()),
    path(
        "<str:id>/candidates/<str:candidate_id>/recommendation/",
        views.CandidateRecommendation.as_view(),
    ),
    path("<str:id>/processing/", views.ProjectProcessing.as_view()),
]
