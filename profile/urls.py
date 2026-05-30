from django.urls import path
from .views import (
    PatientProfileView,
    PatientAppointmentListView,
    PatientReviewListView,
    FavoriteListCreateView,
    FavoriteDeleteView,
)

urlpatterns = [
    path('', PatientProfileView.as_view(), name='patient-profile'),
    path('appointments/', PatientAppointmentListView.as_view(), name='patient-appointments'),
    path('reviews/', PatientReviewListView.as_view(), name='patient-reviews'),
    path('favorites/', FavoriteListCreateView.as_view(), name='patient-favorites'),
    path('favorites/<int:pk>/', FavoriteDeleteView.as_view(), name='patient-favorite-delete'),
]
