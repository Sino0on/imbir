from django.urls import path
from .views import ClinicListView, ClinicDetailView, ClinicProfileViewView

urlpatterns = [
    path('', ClinicListView.as_view(), name='clinic-list'),
    path('<int:pk>/', ClinicDetailView.as_view(), name='clinic-detail'),
    path('<int:pk>/view/', ClinicProfileViewView.as_view(), name='clinic-profile-view'),
]
