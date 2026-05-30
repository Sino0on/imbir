from django.db import models
from users.models import User, DoctorProfile, ClinicProfile
from services.models import Service


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает подтверждения'
        CONFIRMED = 'confirmed', 'Подтверждён'
        CANCELLED = 'cancelled', 'Отменён'
        COMPLETED = 'completed', 'Завершён'

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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Запись на приём'
        verbose_name_plural = 'Записи на приём'
        ordering = ['-created_at']

    def __str__(self):
        who = self.patient.full_name if self.patient else self.guest_name
        return f'{who} — {self.date} {self.time}'
