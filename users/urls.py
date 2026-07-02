from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView, LogoutView, MeView, ClientRegisterView, DoctorRegisterView, ClinicRegisterView,
    PasswordResetRequestView, PasswordResetConfirmView, PasswordResetVerifyView,
    PhoneRegisterRequestView, PhoneRegisterConfirmView
)

urlpatterns = [
    path('register/client/', ClientRegisterView.as_view(), name='auth-register-client'),
    path('register/doctor/', DoctorRegisterView.as_view(), name='auth-register-doctor'),
    path('register/clinic/', ClinicRegisterView.as_view(), name='auth-register-clinic'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('password-reset/verify/', PasswordResetVerifyView.as_view(), name='auth-password-reset-verify'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    path('register/phone/request/', PhoneRegisterRequestView.as_view(), name='auth-register-phone-request'),
    path('register/phone/confirm/', PhoneRegisterConfirmView.as_view(), name='auth-register-phone-confirm'),
]
