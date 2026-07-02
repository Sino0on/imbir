from django.urls import path
from .views import DoctorListView, DoctorDetailView, DoctorAvailableSlotsView

urlpatterns = [
    path('', DoctorListView.as_view(), name='doctor-list'),
    path('<int:pk>/', DoctorDetailView.as_view(), name='doctor-detail'),
    path('<int:pk>/available-slots/', DoctorAvailableSlotsView.as_view(), name='doctor-available-slots'),
]
