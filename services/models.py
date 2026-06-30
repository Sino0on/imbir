from django.db import models
from users.models import ClinicProfile, DoctorProfile


class Service(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)  # минуты
    clinic = models.ForeignKey(
        ClinicProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='services',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.category} — {self.name}'
