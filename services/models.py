from django.db import models
from users.models import ClinicBranch, ClinicProfile, DoctorProfile


class Service(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)  # минуты
    photo = models.ImageField(upload_to='services/photos/', null=True, blank=True)
    clinic = models.ForeignKey(
        ClinicProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='services',
    )
    # Филиал, где проводится процедура (если отличается от основного адреса клиники).
    branch = models.ForeignKey(
        ClinicBranch, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='services',
    )
    # Собственный график процедуры, если отличается от общего графика клиники/филиала.
    # Формат — как schedule/lunch_break у ClinicProfile/DoctorProfile:
    # {"monday": {"enabled": true, "from": "09:00", "to": "18:00"}, ...}
    schedule = models.JSONField(default=dict, null=True, blank=True)
    lunch_break = models.JSONField(default=dict, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.category} — {self.name}'
