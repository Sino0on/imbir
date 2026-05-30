from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView, LogoutView, MeView, ClientRegisterView, DoctorRegisterView, ClinicRegisterView

urlpatterns = [
    path('register/client/', ClientRegisterView.as_view(), name='auth-register-client'),
    path('register/doctor/', DoctorRegisterView.as_view(), name='auth-register-doctor'),
    path('register/clinic/', ClinicRegisterView.as_view(), name='auth-register-clinic'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
]
