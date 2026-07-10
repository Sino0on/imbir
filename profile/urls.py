from django.urls import path
from .views import (
    PatientProfileView,
    PatientAppointmentListView,
    PatientReviewListView,
    FavoriteListCreateView,
)

urlpatterns = [
    path('', PatientProfileView.as_view(), name='patient-profile'),
    path('appointments/', PatientAppointmentListView.as_view(), name='patient-appointments'),
    path('reviews/', PatientReviewListView.as_view(), name='patient-reviews'),
    path('favorites/', FavoriteListCreateView.as_view(), name='patient-favorites'),
]
