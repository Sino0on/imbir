from django.urls import path
from .views import (
    DoctorListView, DoctorDetailView, DoctorAvailableSlotsView, DoctorAvailableDatesView,
    BulkDoctorPhotoUploadView,
    DoctorProfileViewView,
)

urlpatterns = [
    path('', DoctorListView.as_view(), name='doctor-list'),
    path('bulk-photo-upload/', BulkDoctorPhotoUploadView.as_view(), name='doctor-bulk-photo-upload'),
    path('<int:pk>/', DoctorDetailView.as_view(), name='doctor-detail'),
    path('<int:pk>/view/', DoctorProfileViewView.as_view(), name='doctor-profile-view'),
    path('<int:pk>/available-slots/', DoctorAvailableSlotsView.as_view(), name='doctor-available-slots'),
    path('<int:pk>/available-dates/', DoctorAvailableDatesView.as_view(), name='doctor-available-dates'),
]
