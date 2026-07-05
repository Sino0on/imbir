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
                
        if clinic_id:
            try:
                clinic = ClinicProfile.objects.select_related('user').get(user_id=clinic_id)
            except ClinicProfile.DoesNotExist:
                raise serializers.ValidationError({'clinic_id': 'Клиника не найдена.'})
                
            if not clinic.user.is_active or not clinic.is_published:
                raise serializers.ValidationError({'clinic_id': 'Выбранная клиника не принимает записи (не опубликована).'})
                
        return data

    def create(self, validated_data):
        from users.models import DoctorProfile, ClinicProfile
        from services.models import Service
        from .utils import generate_meet_link

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
            )

        appointment = Appointment.objects.create(**validated_data)

        if (appointment.is_online and appointment.patient
                and appointment.doctor and appointment.doctor.user):
            self._notify_chat(appointment)

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
            'status', 'notes',
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


class AppointmentCancelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ('status',)

    def validate_status(self, value):
        if value != Appointment.Status.CANCELLED:
            raise serializers.ValidationError('Можно установить только статус cancelled.')
        if self.instance.status == Appointment.Status.CANCELLED:
            raise serializers.ValidationError('Запись уже отменена.')
        if self.instance.status == Appointment.Status.COMPLETED:
            raise serializers.ValidationError('Нельзя отменить завершённую запись.')
        return value
