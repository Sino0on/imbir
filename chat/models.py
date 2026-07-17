from django.db import models
from users.models import User


class ChatRoom(models.Model):
    participants = models.ManyToManyField(User, related_name='chat_rooms')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Чат-комната'
        verbose_name_plural = 'Чат-комнаты'

    def __str__(self):
        names = ', '.join(p.full_name for p in self.participants.all()[:3])
        return f'Room #{self.pk} [{names}]'


class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender} → Room #{self.room_id}: {self.content[:50]}'


# AI chat messages (room 0 — отдельный чат с ИИ для каждого пользователя)
class AIMessage(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'Пользователь'
        ASSISTANT = 'assistant', 'Ассистент'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_messages')
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    # Рекомендованные сущности: {"doctors": [ids], "clinics": [ids], "services": [ids]}.
    # Храним только id — карточки пересобираются при выдаче из свежих данных.
    recommendations = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Сообщение ИИ-чата'
        verbose_name_plural = 'Сообщения ИИ-чата'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user} [{self.role}]: {self.content[:50]}'
