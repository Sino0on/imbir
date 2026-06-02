from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'title', 'is_read', 'created_at')
    list_filter = ('type', 'is_read')
    search_fields = ('user__email', 'title', 'body')
    readonly_fields = ('created_at',)
    list_per_page = 30

    actions = ['mark_as_read']

    @admin.action(description='Отметить как прочитанные')
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
