from django.urls import path

from . import views

urlpatterns = [
    path("<str:package_id>/", views.DownloadPackageStatus.as_view()),
    path("<str:package_id>/file/", views.DownloadPackageFile.as_view()),
]
