from rest_framework import status
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Appointment
from .serializers import AppointmentCreateSerializer, AppointmentSerializer, AppointmentCancelSerializer


class AppointmentCreateView(CreateAPIView):
    permission_classes = (AllowAny,)
    serializer_class = AppointmentCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save()
        return Response(
            AppointmentSerializer(appointment, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class AppointmentDetailView(RetrieveUpdateAPIView):
    permission_classes = (AllowAny,)
    http_method_names = ['get', 'patch']

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return AppointmentCancelSerializer
        return AppointmentSerializer

    def get_object(self):
        appointment = get_object_or_404(
            Appointment.objects.select_related('patient', 'doctor__user', 'clinic', 'service'),
            pk=self.kwargs['pk'],
        )
        user = self.request.user
        if appointment.patient is not None:
            if not user.is_authenticated:
                raise PermissionDenied('Нет доступа к этой записи.')
            
            is_patient = appointment.patient == user
            is_doctor = appointment.doctor and appointment.doctor.user == user
            is_clinic = appointment.clinic and appointment.clinic.user == user
            
            if not (is_patient or is_doctor or is_clinic):
                raise PermissionDenied('Нет доступа к этой записи.')
        else:
            if user.is_authenticated:
                if user.role == 'doctor':
                    is_doctor = appointment.doctor and appointment.doctor.user == user
                    if not is_doctor:
                        raise PermissionDenied('Нет доступа к этой записи.')
                elif user.role == 'clinic':
                    is_clinic = appointment.clinic and appointment.clinic.user == user
                    if not is_clinic:
                        raise PermissionDenied('Нет доступа к этой записи.')
        return appointment

    def update(self, request, *args, **kwargs):
        appointment = self.get_object()
        serializer = self.get_serializer(appointment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            AppointmentSerializer(appointment, context={'request': request}).data,
        )
