from django.contrib import admin
from django.utils.html import format_html

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price_display', 'duration_display', 'clinic', 'doctors_list', 'active_badge')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'category', 'clinic__name')
    list_per_page = 30

    fieldsets = (
        ('Услуга', {'fields': ('name', 'category', 'description', 'is_active')}),
        ('Параметры', {'fields': ('price', 'duration')}),
        ('Привязка', {'fields': ('clinic',)}),
    )

    @admin.display(description='Врачи')
    def doctors_list(self, obj):
        return ", ".join([d.user.full_name for d in obj.doctors.all()])

    @admin.display(description='Цена')
    def price_display(self, obj):
        if obj.price is None:
            return '—'
        return f'{obj.price} сом'

    @admin.display(description='Длительность')
    def duration_display(self, obj):
        if obj.duration is None:
            return '—'
        return f'{obj.duration} мин'

    @admin.display(description='Активна', boolean=True)
    def active_badge(self, obj):
        return obj.is_active
