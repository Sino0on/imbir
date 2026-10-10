from rest_framework import status
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Appointment
from .serializers import (
    AppointmentCreateSerializer,
    AppointmentSerializer,
    AppointmentStatusUpdateSerializer,
    AppointmentRescheduleSerializer,
    is_patient_side,
)
from .utils import appointment_duration_minutes, generate_meet_link


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
            return AppointmentStatusUpdateSerializer
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


class AppointmentRescheduleView(APIView):
    permission_classes = (AllowAny,)

    def get_object(self, pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related('patient', 'doctor__user', 'clinic', 'service'),
            pk=pk,
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

    def post(self, request, pk):
        appointment = self.get_object(pk)
        serializer = AppointmentRescheduleSerializer(data=request.data, context={'appointment': appointment})
        serializer.is_valid(raise_exception=True)

        new_date = serializer.validated_data['date']
        new_time = serializer.validated_data['time']

        actor_is_patient = is_patient_side(appointment, request.user)

        appointment.date = new_date
        appointment.time = new_time

        # Пациент перенёс уже подтверждённую запись — новое время врач ещё не
        # видел, поэтому запись снова ждёт подтверждения, а не остаётся
        # «подтверждённой» на время, которое никто не подтверждал.
        if actor_is_patient and appointment.status == Appointment.Status.CONFIRMED:
            appointment.status = Appointment.Status.PENDING

        # If online, regenerate Google Meet link
        if appointment.is_online:
            appointment.google_meet_link = generate_meet_link(
                new_date, new_time,
                duration_minutes=appointment_duration_minutes(appointment.service),
            )
            # Консультация на новое время начинается с чистого листа: иначе после
            # переноса уже начатой/завершённой встречи в комнату не пустит
            # (consultation_status=finished), а запись дорожек не стартует —
            # handle_track_published считает её уже запущенной по старому egress_id.
            appointment.consultation_status = Appointment.ConsultationStatus.CREATED
            appointment.doctor_joined = False
            appointment.patient_joined = False
            appointment.started_at = None
            appointment.ended_at = None
            for role in ('doctor', 'patient'):
                setattr(appointment, f'{role}_egress_id', '')
                setattr(appointment, f'{role}_egress_status', '')
                # Ссылка на старую запись иначе выдала бы новую дорожку за
                # готовую ещё до прихода её вебхука (tasks._role_ready).
                setattr(appointment, f'{role}_recording_url', '')

        appointment.save()

        # System message notification in chat if applicable
        if appointment.is_online and appointment.patient and appointment.doctor and appointment.doctor.user:
            try:
                from chat.services import get_or_create_room, send_system_message
                room = get_or_create_room(appointment.patient, appointment.doctor.user)
                date_str = new_date.strftime('%d.%m.%Y')
                time_str = new_time.strftime('%H:%M')
                content = f'Запись на приём перенесена на {date_str} в {time_str}.'
                if appointment.google_meet_link:
                    content += f' Ссылка на видеовстречу: {appointment.google_meet_link}'
                send_system_message(room, content)
            except Exception:
                pass

        self._notify_reschedule(appointment, actor_is_patient)

        return Response(AppointmentSerializer(appointment, context={'request': request}).data)

    def _notify_reschedule(self, appointment, actor_is_patient):
        """Перенос раньше был «тихим»: о новом времени узнавали только из чата и
        только для онлайн-записей. Теперь пишем второй стороне — врачу и клинике,
        если перенёс пациент, и пациенту (гостю — SMS/почтой), если врач/клиника."""
        from notifications.models import Notification
        from notifications.utils import notify, notify_guest, appointment_payload

        date_str = appointment.date.strftime('%d.%m.%Y')
        time_str = appointment.time.strftime('%H:%M')
        payload = appointment_payload(appointment)
        title = 'Запись перенесена'

        # Отдельного типа «перенос» нет (новый вариант choices — это миграция),
        # поэтому SYSTEM: payload всё равно ведёт на конкретную запись.
        if actor_is_patient:
            patient_name = appointment.patient.full_name if appointment.patient else appointment.guest_name
            body = f'{patient_name} перенёс(-ла) запись на {date_str} в {time_str}.'
            if appointment.status == Appointment.Status.PENDING:
                body += ' Подтвердите новое время.'
            doctor_user = appointment.doctor.user if appointment.doctor else None
            clinic_user = appointment.clinic.user if appointment.clinic else None
            notify(doctor_user, Notification.Type.SYSTEM, title, body, payload)
            if clinic_user and clinic_user != doctor_user:
                notify(clinic_user, Notification.Type.SYSTEM, title, body, payload)
        else:
            body = f'Ваша запись перенесена на {date_str} в {time_str}.'
            notify(appointment.patient, Notification.Type.SYSTEM, title, body, payload)
            notify_guest(appointment, title, body)
