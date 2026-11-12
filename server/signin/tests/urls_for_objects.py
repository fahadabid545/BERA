"""A list and a detail route (read and delete) for every kind of company object."""

from django.urls import path
from rest_framework import serializers
from rest_framework.generics import (
    DestroyAPIView,
    ListAPIView,
    RetrieveAPIView,
    UpdateAPIView,
)
from rest_framework.response import Response

from companies.models import CompanyUser
from signin.company_views import CompanyObjectView
from signin.tests.models_for_tests import KINDS_OF_OBJECT

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


def serializer_for(model):
    meta = type("Meta", (), {"model": model, "fields": ["id", "title"]})
    return type("Serializer", (serializers.ModelSerializer,), {"Meta": meta})


class Search(CompanyObjectView, ListAPIView):
    """A search is a list narrowed by what was typed; it must never widen past the company."""

    def get_queryset(self):
        return (
            super().get_queryset().filter(title__icontains=self.request.query_params.get("q", ""))
        )


class Download(CompanyObjectView, RetrieveAPIView):
    """Hands out a file link, the way a download or export address would."""

    def retrieve(self, request, *args, **kwargs):
        return Response({"file_link": f"/files/{self.get_object().id}/"})


def views_for(model, allowed_roles):
    shared = {"queryset": model.objects.all(), "serializer_class": serializer_for(model)}
    shared["allowed_roles"] = allowed_roles
    detail = type("Detail", (CompanyObjectView, RetrieveAPIView), dict(shared))
    delete = type("Delete", (CompanyObjectView, DestroyAPIView), dict(shared))
    listing = type("Listing", (CompanyObjectView, ListAPIView), dict(shared))
    return detail, delete, listing


def extra_views_for(model):
    shared = {"queryset": model.objects.all(), "serializer_class": serializer_for(model)}
    return (
        type("Edit", (CompanyObjectView, UpdateAPIView), dict(shared)),
        type("Find", (Search,), dict(shared)),
        type("Get", (Download,), dict(shared)),
    )


USER_VIEW = {
    "queryset": CompanyUser.objects.all(),
    "serializer_class": type(
        "UserSerializer",
        (serializers.ModelSerializer,),
        {"Meta": type("Meta", (), {"model": CompanyUser, "fields": ["id", "name"]})},
    ),
}
UserDetail = type("UserDetail", (CompanyObjectView, RetrieveAPIView), USER_VIEW)
UserList = type("UserList", (CompanyObjectView, ListAPIView), USER_VIEW)


urlpatterns = [
    path("api/users/", UserList.as_view()),
    path("api/users/<str:id>/", UserDetail.as_view()),
]
for name, model in KINDS_OF_OBJECT.items():
    detail, delete, listing = views_for(model, None)
    owner_detail, _, owner_listing = views_for(model, {"owner"})
    edit, find, download = extra_views_for(model)
    slug = name.lower()
    urlpatterns += [
        path(f"api/{slug}s/", listing.as_view()),
        # Fixed words come before the identifier, or "search" would be taken as an identifier.
        path(f"api/{slug}s/search/", find.as_view()),
        path(f"api/{slug}s/live/", listing.as_view()),
        path(f"api/{slug}s/<str:id>/", detail.as_view()),
        path(f"api/{slug}s/<str:id>/delete/", delete.as_view()),
        path(f"api/{slug}s/<str:id>/edit/", edit.as_view()),
        path(f"api/{slug}s/<str:id>/download/", download.as_view()),
        path(f"api/owner-only-{slug}s/", owner_listing.as_view()),
        path(f"api/owner-only-{slug}s/<str:id>/", owner_detail.as_view()),
    ]
