"""A list and a detail route (read and delete) for every kind of company object."""

from django.urls import path
from rest_framework import serializers
from rest_framework.generics import DestroyAPIView, ListAPIView, RetrieveAPIView

from signin.company_views import CompanyObjectView
from signin.tests.models_for_tests import KINDS_OF_OBJECT

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


def serializer_for(model):
    meta = type("Meta", (), {"model": model, "fields": ["id", "title"]})
    return type("Serializer", (serializers.ModelSerializer,), {"Meta": meta})


def views_for(model, allowed_roles):
    shared = {"queryset": model.objects.all(), "serializer_class": serializer_for(model)}
    shared["allowed_roles"] = allowed_roles
    detail = type("Detail", (CompanyObjectView, RetrieveAPIView), dict(shared))
    delete = type("Delete", (CompanyObjectView, DestroyAPIView), dict(shared))
    listing = type("Listing", (CompanyObjectView, ListAPIView), dict(shared))
    return detail, delete, listing


urlpatterns = []
for name, model in KINDS_OF_OBJECT.items():
    detail, delete, listing = views_for(model, None)
    owner_detail, _, owner_listing = views_for(model, {"owner"})
    slug = name.lower()
    urlpatterns += [
        path(f"api/{slug}s/", listing.as_view()),
        path(f"api/{slug}s/<str:id>/", detail.as_view()),
        path(f"api/{slug}s/<str:id>/delete/", delete.as_view()),
        path(f"api/owner-only-{slug}s/", owner_listing.as_view()),
        path(f"api/owner-only-{slug}s/<str:id>/", owner_detail.as_view()),
    ]
