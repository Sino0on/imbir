from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import User, DoctorProfile, ClinicProfile


class Review(models.Model):
    class TargetType(models.TextChoices):
        DOCTOR = 'doctor', 'Врач'
        CLINIC = 'clinic', 'Клиника'

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    appointment = models.OneToOneField(
        'appointments.Appointment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='review',
    )
    target_type = models.CharField(max_length=10, choices=TargetType.choices)
    doctor = models.ForeignKey(
        DoctorProfile, on_delete=models.CASCADE,
        null=True, blank=True, related_name='reviews',
    )
    clinic = models.ForeignKey(
        ClinicProfile, on_delete=models.CASCADE,
        null=True, blank=True, related_name='reviews',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    text = models.TextField(blank=True)
    reply_text = models.TextField(blank=True, null=True)
    reply_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author.full_name} → {self.target_type} ({self.rating}★)'
