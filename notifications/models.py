from django.db import models
from users.models import User


class Notification(models.Model):
    class Type(models.TextChoices):
        APPOINTMENT_REMINDER = 'appointment_reminder', 'Напоминание о записи'
        NEW_REVIEW = 'new_review', 'Новый отзыв'
        NEW_MESSAGE = 'new_message', 'Новое сообщение'
        SYSTEM = 'system', 'Системное'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=30, choices=Type.choices, default=Type.SYSTEM)
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} — {self.title}'
