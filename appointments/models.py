from django.db import models
from users.models import User, DoctorProfile, ClinicProfile
from services.models import Service


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает подтверждения'
        CONFIRMED = 'confirmed', 'Подтверждён'
        CANCELLED = 'cancelled', 'Отменён'
        COMPLETED = 'completed', 'Завершён'

    class ConsultationStatus(models.TextChoices):
        """Статус видео-консультации LiveKit — независим от Status (статус самой записи)."""
        CREATED = 'created', 'Создана'
        WAITING = 'waiting', 'Ожидание участников'
        ACTIVE = 'active', 'Идёт консультация'
        FINISHED = 'finished', 'Завершена'
        CANCELLED = 'cancelled', 'Отменена'

    # Авторизованный пациент (null — гостевая запись)
    patient = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointments',
    )

    # Поля для гостя
    guest_name = models.CharField(max_length=255, blank=True)
    guest_phone = models.CharField(max_length=20, blank=True)
    guest_email = models.EmailField(blank=True)

    doctor = models.ForeignKey(
        DoctorProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointments',
    )
    clinic = models.ForeignKey(
        ClinicProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointments',
    )
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointments',
    )

    date = models.DateField()
    time = models.TimeField()
    is_online = models.BooleanField(default=False)
    google_meet_link = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True, null=True)
    recommendations = models.TextField(blank=True, null=True)
    doctor_notes = models.TextField(blank=True, null=True)

    # Заглушка оплаты: система оплаты ещё не интегрирована, поэтому по умолчанию
    # запись считается оплаченной. Когда появится реальная оплата — выставлять
    # False при создании и True по вебхуку/колбэку платёжной системы.
    is_paid = models.BooleanField(default=True, verbose_name='Оплачено')

    # --- LiveKit ---
    room_name = models.CharField(max_length=255, blank=True, default='', db_index=True)
    livekit_room_created = models.BooleanField(default=False)
    doctor_joined = models.BooleanField(default=False)
    patient_joined = models.BooleanField(default=False)
    consultation_status = models.CharField(
        max_length=20,
        choices=ConsultationStatus.choices,
        default=ConsultationStatus.CREATED,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # --- LiveKit Egress (запись консультации) ---
    egress_id = models.CharField(max_length=255, blank=True, default='')
    egress_status = models.CharField(max_length=32, blank=True, default='')
    recording_url = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Запись на приём'
        verbose_name_plural = 'Записи на приём'
        ordering = ['-created_at']

    def __str__(self):
        who = self.patient.full_name if self.patient else self.guest_name
        return f'{who} — {self.date} {self.time}'
