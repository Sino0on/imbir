from django.urls import path
from .views import AppointmentCreateView, AppointmentCancelView

urlpatterns = [
    path('', AppointmentCreateView.as_view(), name='appointment-create'),
    path('<int:pk>/', AppointmentCancelView.as_view(), name='appointment-cancel'),
]
