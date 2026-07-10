from django.urls import path
from .views import (
    DoctorAppointmentListView,
    DoctorPatientListView,
    DoctorProfileView,
    DoctorReviewListView,
    DoctorScheduleView,
    DoctorServiceDetailView,
    DoctorServiceListCreateView,
    DoctorStatsView,
    DoctorAppointmentSummaryView,
    DoctorDocumentListCreateView,
    DoctorDocumentDeleteView,
    DoctorInterviewListCreateView,
    DoctorInterviewDetailView,
)

urlpatterns = [
    path('profile/', DoctorProfileView.as_view(), name='doctor-own-profile'),
    path('schedule/', DoctorScheduleView.as_view(), name='doctor-schedule'),
    path('appointments/', DoctorAppointmentListView.as_view(), name='doctor-appointments'),
    path('appointments/<int:pk>/summary/', DoctorAppointmentSummaryView.as_view(), name='doctor-appointment-summary'),
    path('patients/', DoctorPatientListView.as_view(), name='doctor-patients'),
    path('stats/', DoctorStatsView.as_view(), name='doctor-stats'),
    path('reviews/', DoctorReviewListView.as_view(), name='doctor-reviews'),
    path('services/', DoctorServiceListCreateView.as_view(), name='doctor-services'),
    path('services/<int:pk>/', DoctorServiceDetailView.as_view(), name='doctor-service-detail'),
    path('documents/', DoctorDocumentListCreateView.as_view(), name='doctor-documents'),
    path('documents/<int:pk>/', DoctorDocumentDeleteView.as_view(), name='doctor-document-delete'),
    path('interviews/', DoctorInterviewListCreateView.as_view(), name='doctor-interviews'),
    path('interviews/<int:pk>/', DoctorInterviewDetailView.as_view(), name='doctor-interview-detail'),
]
