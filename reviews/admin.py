from django.contrib import admin
from django.utils.html import format_html

from .models import Review
from .serializers import _update_rating


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

    # Правка и удаление отзыва в админке должны пересчитывать кэшированные
    # rating/reviews_count врача или клиники — как это делает API. Раньше после
    # удаления отзыва-спама рейтинг оставался прежним.
    def save_model(self, request, obj, form, change):
        old = Review.objects.filter(pk=obj.pk).first() if change else None
        super().save_model(request, obj, form, change)
        _update_rating(obj)
        # Отзыв перенесли на другого врача/клинику — пересчитать и прежнего.
        if old and (old.doctor_id, old.clinic_id, old.target_type) != (
            obj.doctor_id, obj.clinic_id, obj.target_type,
        ):
            _update_rating(old)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        _update_rating(obj)

    def delete_queryset(self, request, queryset):
        reviews = list(queryset.select_related('doctor', 'clinic'))
        super().delete_queryset(request, queryset)
        # Каждую цель — один раз, сколько бы её отзывов ни удалили.
        seen = set()
        for review in reviews:
            target = (review.target_type, review.doctor_id, review.clinic_id)
            if target not in seen:
                seen.add(target)
                _update_rating(review)

    @admin.display(description='Оценка')
    def stars(self, obj):
        filled = '★' * obj.rating
        empty = '☆' * (5 - obj.rating)
        color = '#ffc107' if obj.rating >= 4 else ('#fd7e14' if obj.rating == 3 else '#dc3545')
        return format_html('<span style="color:{};font-size:14px">{}{}</span>', color, filled, empty)
