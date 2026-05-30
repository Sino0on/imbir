from django.urls import path
from .views import (
    DoctorProfileView,
    DoctorScheduleView,
    DoctorAppointmentListView,
    DoctorPatientListView,
    DoctorStatsView,
)

urlpatterns = [
    path('profile/', DoctorProfileView.as_view(), name='doctor-own-profile'),
    path('schedule/', DoctorScheduleView.as_view(), name='doctor-schedule'),
    path('appointments/', DoctorAppointmentListView.as_view(), name='doctor-appointments'),
    path('patients/', DoctorPatientListView.as_view(), name='doctor-patients'),
    path('stats/', DoctorStatsView.as_view(), name='doctor-stats'),
]
