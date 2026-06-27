from django.contrib import admin
from .models import ChatRoom, ChatMessage, AIMessage


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'participant_names', 'created_at')
    list_per_page = 50

    def participant_names(self, obj):
        return ', '.join(p.full_name for p in obj.participants.all())
    participant_names.short_description = 'Участники'


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'content_preview', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('sender__email', 'content')
    list_per_page = 50

    def content_preview(self, obj):
        return obj.content[:80]
    content_preview.short_description = 'Сообщение'


@admin.register(AIMessage)
class AIMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'content_preview', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__email', 'content')
    list_per_page = 50

    def content_preview(self, obj):
        return obj.content[:80]
    content_preview.short_description = 'Сообщение'
