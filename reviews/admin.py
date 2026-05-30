from django.contrib import admin
from django.utils.html import format_html

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('author', 'target_type', 'stars', 'doctor', 'clinic', 'created_at')
    list_filter = ('target_type', 'rating')
    search_fields = ('author__email', 'author__first_name', 'author__last_name', 'text')
    readonly_fields = ('created_at',)
    list_per_page = 30

    fieldsets = (
        ('Отзыв', {'fields': ('author', 'appointment', 'target_type', 'doctor', 'clinic')}),
        ('Содержание', {'fields': ('rating', 'text', 'created_at')}),
    )

    @admin.display(description='Оценка')
    def stars(self, obj):
        filled = '★' * obj.rating
        empty = '☆' * (5 - obj.rating)
        color = '#ffc107' if obj.rating >= 4 else ('#fd7e14' if obj.rating == 3 else '#dc3545')
        return format_html('<span style="color:{};font-size:14px">{}{}</span>', color, filled, empty)
