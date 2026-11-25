from django.urls import path

from . import discount_views

urlpatterns = [
    path("", discount_views.DiscountList.as_view()),
    path("<int:id>/", discount_views.DiscountDetail.as_view()),
]
