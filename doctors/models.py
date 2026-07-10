from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Interview(models.Model):
    doctor = models.ForeignKey(
        'users.DoctorProfile',
        on_delete=models.CASCADE,
        related_name='interviews',
        verbose_name='Врач'
    )
    title = models.CharField(max_length=255, verbose_name='Название')
    video_url = models.URLField(verbose_name='Ссылка на ютуб видео')
    priority = models.PositiveSmallIntegerField(
        choices=[(0, '0'), (1, '1'), (2, '2'), (3, '3')],
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        verbose_name='Приоритет'
    )

    class Meta:
        verbose_name = 'Интервью'
        verbose_name_plural = 'Интервью'
        ordering = ['-priority', 'id']

    def __str__(self):
        # We access self.doctor.user.full_name. Wait, user is a OneToOneField on DoctorProfile.
        # But if the doctor relation is not fully loaded or user is missing (shouldn't happen under normal circumstances),
        # we can safe-guard or keep it simple.
        try:
            return f'{self.title} ({self.doctor.user.full_name})'
        except Exception:
            return self.title
