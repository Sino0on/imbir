from django.urls import path
from .views import AppointmentCreateView, AppointmentDetailView, AppointmentRescheduleView

urlpatterns = [
    path('', AppointmentCreateView.as_view(), name='appointment-create'),
    path('<int:pk>/', AppointmentDetailView.as_view(), name='appointment-detail'),
    path('<int:pk>/reschedule/', AppointmentRescheduleView.as_view(), name='appointment-reschedule'),
]
