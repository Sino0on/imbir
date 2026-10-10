from rest_framework import serializers
from .models import Appointment


class AppointmentCreateSerializer(serializers.ModelSerializer):
    doctor_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    clinic_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    service_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Appointment
        fields = (
            'doctor_id', 'clinic_id', 'service_id',
            'date', 'time', 'notes',
            'guest_name', 'guest_phone', 'guest_email',
            'is_online',
        )

    def validate(self, data):
        request = self.context['request']
        if not request.user.is_authenticated:
            if data.get('is_online'):
                raise serializers.ValidationError(
                    {'is_online': 'Онлайн-запись доступна только авторизованным пользователям.'}
                )
            if not data.get('guest_name'):
                raise serializers.ValidationError({'guest_name': 'Обязательно для гостевой записи.'})
            if not data.get('guest_phone'):
                raise serializers.ValidationError({'guest_phone': 'Обязательно для гостевой записи.'})
        
        doctor_id = data.get('doctor_id')
        clinic_id = data.get('clinic_id')
        
        if not doctor_id and not clinic_id:
            raise serializers.ValidationError('Укажите doctor_id или clinic_id.')

        from users.models import DoctorProfile, ClinicProfile
        from services.models import Service
        from .utils import appointment_start_is_past

        # Для любой записи, в том числе без врача (только в клинику).
        if appointment_start_is_past(data['date'], data['time']):
            raise serializers.ValidationError(
                {'time': 'Это время уже прошло — выберите другое.'}
            )

        # Услугу, которую не нашли или сняли с записи, раньше молча выкидывали —
        # запись создавалась «ни на что». Теперь это ошибка.
        service = None
        service_id = data.get('service_id')
        if service_id:
            service = Service.objects.filter(id=service_id, is_active=True).first()
            if service is None:
                raise serializers.ValidationError(
                    {'service_id': 'Услуга не найдена или сейчас недоступна для записи.'}
                )

        clinic = None
        if clinic_id:
            try:
                clinic = ClinicProfile.objects.select_related('user').get(user_id=clinic_id)
            except ClinicProfile.DoesNotExist:
                raise serializers.ValidationError({'clinic_id': 'Клиника не найдена.'})

            if not clinic.user.is_active or not clinic.is_published:
                raise serializers.ValidationError({'clinic_id': 'Выбранная клиника не принимает записи (не опубликована).'})

        # clinic_id — публичный id клиники (ClinicProfile.user_id), а service.clinic_id —
        # pk профиля, поэтому сравниваем с clinic.pk.
        if service and clinic and service.clinic_id and service.clinic_id != clinic.pk:
            raise serializers.ValidationError(
                {'service_id': 'Эта услуга оказывается в другой клинике.'}
            )

        if doctor_id:
            try:
                doctor = DoctorProfile.objects.select_related('user').get(user_id=doctor_id)
            except DoctorProfile.DoesNotExist:
                raise serializers.ValidationError({'doctor_id': 'Врач не найден.'})

            if not doctor.user.is_active or not doctor.is_published:
                raise serializers.ValidationError({'doctor_id': 'Выбранный врач не принимает записи (не опубликован).'})

            if data.get('is_online') and not doctor.is_online_available:
                raise serializers.ValidationError(
                    {'is_online': 'Этот врач не проводит онлайн-консультации.'}
                )

            if clinic and not doctor.clinic_links.filter(clinic=clinic, is_active=True).exists():
                raise serializers.ValidationError(
                    {'clinic_id': 'Этот врач не принимает в выбранной клинике.'}
                )

            if service and not self._service_available_for_doctor(service, doctor):
                raise serializers.ValidationError(
                    {'service_id': 'Этот врач не оказывает выбранную услугу.'}
                )

            from .utils import find_overlapping_appointment, schedule_conflict
            # Вся длительность услуги должна помещаться в рабочий день врача и не
            # задевать перерыв — по тем же правилам, по которым считаются слоты.
            problem = schedule_conflict(doctor, data['date'], data['time'], service)
            if problem:
                raise serializers.ValidationError({'time': problem})

            conflict = find_overlapping_appointment(doctor, data['date'], data['time'], service)
            if conflict:
                raise serializers.ValidationError(
                    {'time': 'Врач уже занят в это время — выберите другой слот.'}
                )

        # Запись только в клинику (без врача) пока не проверяется по графику и
        # пересечениям — у клиники нет своей сетки слотов (см. K6/K9).
        return data

    @staticmethod
    def _service_available_for_doctor(service, doctor):
        """Услуга врача — или услуга клиники, не закреплённая ни за одним врачом
        (её, как и форма записи на фронте, может оказать любой врач этой клиники)."""
        if doctor.services.filter(pk=service.pk).exists():
            return True
        if service.clinic_id is None or service.doctors.exists():
            return False
        return doctor.clinic_links.filter(clinic_id=service.clinic_id, is_active=True).exists()

    def create(self, validated_data):
        from users.models import DoctorProfile, ClinicProfile
        from services.models import Service
        from .utils import appointment_duration_minutes, generate_meet_link

        doctor_id = validated_data.pop('doctor_id', None)
        clinic_id = validated_data.pop('clinic_id', None)
        service_id = validated_data.pop('service_id', None)

        request = self.context['request']
        if request.user.is_authenticated:
            validated_data['patient'] = request.user

        if doctor_id:
            validated_data['doctor'] = DoctorProfile.objects.filter(user_id=doctor_id).first()
        if clinic_id:
            validated_data['clinic'] = ClinicProfile.objects.filter(user_id=clinic_id).first()
        if service_id:
            validated_data['service'] = Service.objects.filter(id=service_id).first()

        if validated_data.get('is_online'):
            validated_data['google_meet_link'] = generate_meet_link(
                validated_data['date'],
                validated_data['time'],
                duration_minutes=appointment_duration_minutes(validated_data.get('service')),
            )

        appointment = Appointment.objects.create(**validated_data)

        if (appointment.is_online and appointment.patient
                and appointment.doctor and appointment.doctor.user):
            self._notify_chat(appointment)

        self._notify_new_appointment(appointment)

        return appointment

    def _notify_chat(self, appointment):
        from chat.services import get_or_create_room, send_system_message

        room = get_or_create_room(appointment.patient, appointment.doctor.user)
        date_str = appointment.date.strftime('%d.%m.%Y')
        time_str = appointment.time.strftime('%H:%M')
        content = f'Создана онлайн-запись на {date_str} в {time_str}.'
        if appointment.google_meet_link:
            content += f' Ссылка на видеовстречу: {appointment.google_meet_link}'
        send_system_message(room, content)

    def _notify_new_appointment(self, appointment):
        from notifications.models import Notification
        from notifications.utils import notify, appointment_payload

        date_str = appointment.date.strftime('%d.%m.%Y')
        time_str = appointment.time.strftime('%H:%M')
        patient_name = appointment.patient.full_name if appointment.patient else appointment.guest_name
        title = 'Новая запись'
        body = f'{patient_name} записался(-ась) на {date_str} в {time_str}.'
        payload = appointment_payload(appointment)

        doctor_user = appointment.doctor.user if appointment.doctor else None
        clinic_user = appointment.clinic.user if appointment.clinic else None
        notify(doctor_user, Notification.Type.APPOINTMENT_CREATED, title, body, payload)
        if clinic_user and clinic_user != doctor_user:
            notify(clinic_user, Notification.Type.APPOINTMENT_CREATED, title, body, payload)


class AppointmentSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    doctor = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = (
            'id', 'patient',
            'guest_name', 'guest_phone', 'guest_email',
            'doctor', 'clinic', 'service',
            'date', 'time', 'is_online', 'google_meet_link',
            'status', 'notes', 'ai_summary',
            'ai_summary_docx_url', 'diagnosis', 'recommendations', 'doctor_notes',
            'created_at',
        )

    def get_patient(self, obj):
        if not obj.patient:
            return None
        return {
            'id': obj.patient.id,
            'full_name': obj.patient.full_name,
            'phone': obj.patient.phone,
            'email': obj.patient.email,
        }

    def get_doctor(self, obj):
        if not obj.doctor:
            return None
        return {
            'id': obj.doctor.user_id,
            'full_name': obj.doctor.user.full_name,
        }

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        return {
            'id': obj.clinic.user_id,
            'name': obj.clinic.name,
        }

    def get_service(self, obj):
        if not obj.service:
            return None
        return {
            'id': obj.service.id,
            'name': obj.service.name,
            'price': obj.service.price,
        }


# Из какого статуса в какие можно переходить. completed/cancelled — конечные,
# дальше не меняются (переносить/отменять/завершать завершённую или отменённую
# запись нельзя).
_ALLOWED_STATUS_TRANSITIONS = {
    Appointment.Status.PENDING: {
        Appointment.Status.CONFIRMED, Appointment.Status.COMPLETED, Appointment.Status.CANCELLED,
    },
    Appointment.Status.CONFIRMED: {
        Appointment.Status.COMPLETED, Appointment.Status.CANCELLED,
    },
}

# Пациент может только отменить свою запись — подтверждать/завершать приём
# может только врач или клиника.
_PATIENT_ALLOWED_STATUSES = {Appointment.Status.CANCELLED}


def is_patient_side(appointment, user):
    """Действие совершает пациентская сторона записи, а не её врач или клиника.
    У авторизованной записи это её владелец; у гостевой — любой, кто не врач и
    не клиника этой записи (у гостя нет аккаунта, а AppointmentDetailView/
    AppointmentRescheduleView пускают к гостевой записи без авторизации)."""
    is_authenticated = bool(user) and getattr(user, 'is_authenticated', False)
    if appointment.patient_id is not None:
        return is_authenticated and appointment.patient_id == user.id
    if not is_authenticated:
        return True
    is_doctor = appointment.doctor is not None and appointment.doctor.user_id == user.id
    is_clinic = appointment.clinic is not None and appointment.clinic.user_id == user.id
    return not (is_doctor or is_clinic)


class AppointmentStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ('status',)

    def validate_status(self, value):
        appointment = self.instance
        current = appointment.status

        if value == current:
            raise serializers.ValidationError('Запись уже в этом статусе.')

        allowed_next = _ALLOWED_STATUS_TRANSITIONS.get(current, set())
        if value not in allowed_next:
            raise serializers.ValidationError(
                f'Нельзя перевести запись из статуса "{appointment.get_status_display()}" '
                f'в "{Appointment.Status(value).label}".'
            )

        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if is_patient_side(appointment, user) and value not in _PATIENT_ALLOWED_STATUSES:
            raise serializers.ValidationError('Пациент может только отменить запись.')

        # Завершить можно только начавшийся приём — иначе пациент получал
        # «Приём завершён, оставьте отзыв» ещё до визита и мог оставить отзыв.
        if value == Appointment.Status.COMPLETED:
            from .utils import appointment_start_is_past
            if not appointment_start_is_past(appointment.date, appointment.time):
                raise serializers.ValidationError('Нельзя завершить приём, который ещё не начался.')

        return value

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._notify_status_change(instance)
        return instance

    def _notify_status_change(self, appointment):
        from notifications.models import Notification
        from notifications.utils import notify, notify_guest, appointment_payload

        date_str = appointment.date.strftime('%d.%m.%Y')
        time_str = appointment.time.strftime('%H:%M')
        payload = appointment_payload(appointment)

        request = self.context.get('request')
        actor = getattr(request, 'user', None)
        actor_is_patient = is_patient_side(appointment, actor)

        patient_user = appointment.patient
        doctor_user = appointment.doctor.user if appointment.doctor else None
        clinic_user = appointment.clinic.user if appointment.clinic else None

        if appointment.status == Appointment.Status.CONFIRMED:
            title = 'Запись подтверждена'
            body = f'Ваша запись на {date_str} в {time_str} подтверждена.'
            notify(patient_user, Notification.Type.APPOINTMENT_CONFIRMED, title, body, payload)
            notify_guest(appointment, title, body)
        elif appointment.status == Appointment.Status.CANCELLED:
            title = 'Запись отменена'
            if actor_is_patient:
                body = f'Пациент отменил запись на {date_str} в {time_str}.'
                notify(doctor_user, Notification.Type.APPOINTMENT_CANCELLED, title, body, payload)
                notify(clinic_user, Notification.Type.APPOINTMENT_CANCELLED, title, body, payload)
            else:
                body = f'Ваша запись на {date_str} в {time_str} отменена.'
                notify(patient_user, Notification.Type.APPOINTMENT_CANCELLED, title, body, payload)
                notify_guest(appointment, title, body)
        elif appointment.status == Appointment.Status.COMPLETED:
            notify(
                patient_user, Notification.Type.APPOINTMENT_COMPLETED,
                'Приём завершён',
                'Приём завершён. Будем рады, если оставите отзыв о враче.',
                payload,
            )


class AppointmentRescheduleSerializer(serializers.Serializer):
    date = serializers.DateField(required=True)
    time = serializers.TimeField(required=True)

    def validate(self, data):
        appointment = self.context.get('appointment')
        if not appointment:
            raise serializers.ValidationError('Запись не найдена.')

        if appointment.status == Appointment.Status.CANCELLED:
            raise serializers.ValidationError('Нельзя перенести отменённую запись.')
        if appointment.status == Appointment.Status.COMPLETED:
            raise serializers.ValidationError('Нельзя перенести завершённую запись.')

        from .utils import appointment_start_is_past
        if appointment_start_is_past(data['date'], data['time']):
            raise serializers.ValidationError(
                {'time': 'Это время уже прошло — выберите другое.'}
            )

        if appointment.doctor:
            from .utils import find_overlapping_appointment, schedule_conflict
            problem = schedule_conflict(
                appointment.doctor, data['date'], data['time'], appointment.service,
            )
            if problem:
                raise serializers.ValidationError({'time': problem})

            conflict = find_overlapping_appointment(
                appointment.doctor, data['date'], data['time'], appointment.service,
                exclude_id=appointment.id,
            )
            if conflict:
                raise serializers.ValidationError(
                    {'time': 'Врач уже занят в это время — выберите другой слот.'}
                )

        return data
