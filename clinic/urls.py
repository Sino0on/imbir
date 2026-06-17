from django.urls import path
from .views import (
    BranchUpdateView,
    ClinicAppointmentListView,
    ClinicDoctorListView,
    ClinicDoctorUnlinkView,
    ClinicProfileView,
    ClinicReviewListView,
    ClinicServiceDetailView,
    ClinicServiceListCreateView,
    ClinicStatsView,
    InviteDeleteView,
    InviteListCreateView,
)

urlpatterns = [
    path('profile/', ClinicProfileView.as_view(), name='clinic-own-profile'),
    path('appointments/', ClinicAppointmentListView.as_view(), name='clinic-appointments'),
    path('stats/', ClinicStatsView.as_view(), name='clinic-stats'),
    path('reviews/', ClinicReviewListView.as_view(), name='clinic-reviews'),
    path('doctors/', ClinicDoctorListView.as_view(), name='clinic-doctors'),
    path('doctors/<int:pk>/', ClinicDoctorUnlinkView.as_view(), name='clinic-doctor-unlink'),
    path('services/', ClinicServiceListCreateView.as_view(), name='clinic-services'),
    path('services/<int:pk>/', ClinicServiceDetailView.as_view(), name='clinic-service-detail'),
    path('branches/<int:pk>/', BranchUpdateView.as_view(), name='clinic-branch-update'),
    path('invites/', InviteListCreateView.as_view(), name='clinic-invite-list-create'),
    path('invites/<uuid:pk>/', InviteDeleteView.as_view(), name='clinic-invite-delete'),
]
