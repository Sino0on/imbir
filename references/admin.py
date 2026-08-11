from django.contrib import admin

from .models import Specialization, Tag, SiteSettings


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_per_page = 100


@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    list_per_page = 200


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Соцсети', {'fields': ('facebook_url', 'instagram_url', 'twitter_url', 'linkedin_url')}),
        ('Контакты', {'fields': ('contact_email', 'contact_phone', 'address')}),
        ('Юридические тексты', {'fields': ('terms_text', 'privacy_policy_text')}),
    )

    def has_add_permission(self, request):
        # Синглтон: одна запись, дальше — только редактирование существующей.
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
