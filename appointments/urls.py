from django.urls import path
from .views import AppointmentCreateView, AppointmentDetailView

urlpatterns = [
    path('', AppointmentCreateView.as_view(), name='appointment-create'),
    path('<int:pk>/', AppointmentDetailView.as_view(), name='appointment-detail'),
]
