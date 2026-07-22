from django.contrib import admin
from django.utils.html import format_html

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient_display', 'doctor', 'clinic', 'date', 'time',
                    'format_badge', 'status_badge', 'created_at')
    list_filter = ('status', 'is_online', 'date')
    search_fields = ('guest_name', 'guest_phone', 'guest_email',
                     'patient__email', 'patient__first_name', 'patient__last_name')
    readonly_fields = (
        'created_at', 'updated_at',
        'room_name', 'livekit_room_created', 'doctor_joined', 'patient_joined',
        'consultation_status', 'started_at', 'ended_at',
        'egress_id', 'egress_status', 'recording_url',
    )
    date_hierarchy = 'date'
    list_per_page = 30

    fieldsets = (
        ('Пациент', {'fields': ('patient', 'guest_name', 'guest_phone', 'guest_email')}),
        ('Запись', {'fields': ('doctor', 'clinic', 'service', 'date', 'time', 'is_online', 'status', 'is_paid')}),
        ('LiveKit — консультация', {'fields': (
            'room_name', 'livekit_room_created', 'doctor_joined', 'patient_joined',
            'consultation_status', 'started_at', 'ended_at',
        )}),
        ('LiveKit — запись', {'fields': ('egress_id', 'egress_status', 'recording_url')}),
        ('Дополнительно', {'fields': ('notes', 'created_at', 'updated_at')}),
    )

    @admin.display(description='Пациент')
    def patient_display(self, obj):
        if obj.patient:
            return obj.patient.full_name
        return f'{obj.guest_name} (гость)'

    @admin.display(description='Статус')
    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'confirmed': '#28a745',
            'cancelled': '#dc3545',
            'completed': '#17a2b8',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.display(description='Формат')
    def format_badge(self, obj):
        if obj.is_online:
            return format_html('<span style="color:#17a2b8">{}</span>', '🌐 Онлайн')
        return format_html('<span style="color:#6c757d">{}</span>', '🏠 Офлайн')

