from django.urls import path
from .views import ClinicListView, ClinicDetailView

urlpatterns = [
    path('', ClinicListView.as_view(), name='clinic-list'),
    path('<int:pk>/', ClinicDetailView.as_view(), name='clinic-detail'),
]
