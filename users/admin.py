from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    ClinicBranch, ClinicDocument, ClinicInvite, ClinicPhoto, ClinicProfile,
    DoctorClinicLink, DoctorDocument, DoctorProfile, Favorite, PatientProfile, User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name', 'role_badge', 'phone', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'phone', 'role')}),
        ('Права доступа', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
                           'classes': ('collapse',)}),
        ('Даты', {'fields': ('last_login', 'date_joined'), 'classes': ('collapse',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone', 'role', 'password1', 'password2'),
        }),
    )
    readonly_fields = ('date_joined', 'last_login')

    @admin.display(description='Роль')
    def role_badge(self, obj):
        colors = {
            'patient': '#17a2b8',
            'doctor': '#28a745',
            'clinic': '#6f42c1',
            'admin': '#dc3545',
        }
        color = colors.get(obj.role, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_role_display(),
        )


class DoctorDocumentInline(admin.TabularInline):
    model = DoctorDocument
    extra = 0
    readonly_fields = ('uploaded_at',)


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'license_number', 'rating', 'reviews_count',
                    'profile_views', 'published_badge', 'created_at')
    list_filter = ('is_published', 'emergency_24_7', 'city', 'is_online_available')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'license_number', 'city')
    readonly_fields = ('rating', 'reviews_count', 'profile_views', 'created_at', 'updated_at')
    inlines = (DoctorDocumentInline,)
    list_per_page = 25

    fieldsets = (
        ('Основное', {'fields': ('user', 'gender', 'birth_date', 'city', 'languages', 'photo')}),
        ('Локация', {'fields': ('country', 'address', 'website', 'latitude', 'longitude')}),
        ('Расписание', {'fields': ('schedule', 'lunch_break', 'emergency_24_7')}),
        ('Юридические данные', {'fields': ('legal_name', 'reg_number', 'license_number',
                                            'license_date', 'license_authority')}),
        ('Специализация', {'fields': ('primary_specializations', 'narrow_specializations', 'additional_services')}),
        ('Условия', {'fields': ('equipment', 'patient_conditions', 'payment_methods')}),
        ('Публичный профиль', {'fields': ('about', 'experience_years', 'is_online_available',
                                          'consultation_price', 'is_published')}),
        ('Биография', {'fields': ('education', 'work_experience', 'skills'), 'classes': ('collapse',)}),
        ('Статистика', {'fields': ('rating', 'reviews_count', 'profile_views', 'created_at', 'updated_at'),
                        'classes': ('collapse',)}),
        ('Согласия', {'fields': ('agree_terms', 'agree_privacy', 'agree_data_processing', 'agree_publishing'),
                      'classes': ('collapse',)}),
    )

    @admin.display(description='Опубликован', boolean=True)
    def published_badge(self, obj):
        return obj.is_published


class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'blood_type', 'emergency_contact_name', 'updated_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'emergency_contact_name')
    readonly_fields = ('updated_at',)


admin.site.register(PatientProfile, PatientProfileAdmin)


class ClinicPhotoInline(admin.TabularInline):
    model = ClinicPhoto
    extra = 0
    readonly_fields = ('uploaded_at',)


class ClinicDocumentInline(admin.TabularInline):
    model = ClinicDocument
    extra = 0
    readonly_fields = ('uploaded_at',)


class ClinicBranchInline(admin.TabularInline):
    model = ClinicBranch
    extra = 0
    fields = ('name', 'address', 'phone')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(ClinicProfile)
class ClinicProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'clinic_type', 'rating', 'reviews_count',
                    'doctors_count', 'published_badge', 'created_at')
    list_filter = ('is_published', 'emergency_24_7', 'city')
    search_fields = ('name', 'email', 'license_number', 'user__email')
    readonly_fields = ('rating', 'reviews_count', 'doctors_count', 'profile_views', 'created_at', 'updated_at')
    inlines = (ClinicBranchInline, ClinicPhotoInline, ClinicDocumentInline)
    list_per_page = 25

    fieldsets = (
        ('Основное', {'fields': ('user', 'name', 'clinic_type', 'description', 'logo')}),
        ('Контакты и локация', {'fields': ('country', 'city', 'address', 'phone', 'email', 'website',
                                            'latitude', 'longitude')}),
        ('Расписание', {'fields': ('schedule', 'lunch_break', 'emergency_24_7')}),
        ('Юридические данные', {'fields': ('legal_name', 'reg_number', 'license_number',
                                            'license_date', 'license_authority')}),
        ('Специализация', {'fields': ('primary_specializations', 'narrow_specializations', 'additional_services')}),
        ('Условия', {'fields': ('equipment', 'patient_conditions', 'payment_methods')}),
        ('Публичный профиль', {'fields': ('experience_years', 'is_published')}),
        ('Статистика', {'fields': ('rating', 'reviews_count', 'doctors_count', 'profile_views',
                                   'created_at', 'updated_at'), 'classes': ('collapse',)}),
        ('Согласия', {'fields': ('agree_terms', 'agree_privacy', 'agree_data_processing', 'agree_publishing'),
                      'classes': ('collapse',)}),
    )

    @admin.display(description='Опубликована', boolean=True)
    def published_badge(self, obj):
        return obj.is_published


@admin.register(ClinicBranch)
class ClinicBranchAdmin(admin.ModelAdmin):
    list_display = ('clinic', 'name', 'address', 'phone', 'created_at')
    list_filter = ('clinic',)
    search_fields = ('clinic__name', 'address', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClinicInvite)
class ClinicInviteAdmin(admin.ModelAdmin):
    list_display = ('id', 'clinic', 'branch', 'is_active', 'valid_badge', 'expires_at', 'created_at')
    list_filter = ('is_active', 'clinic')
    search_fields = ('clinic__name',)
    readonly_fields = ('id', 'created_at')
    list_per_page = 25

    @admin.display(description='Действителен', boolean=True)
    def valid_badge(self, obj):
        return obj.is_valid


@admin.register(DoctorClinicLink)
class DoctorClinicLinkAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'clinic', 'branch', 'is_active', 'created_at')
    list_filter = ('is_active', 'clinic')
    search_fields = ('doctor__user__email', 'clinic__name')
    readonly_fields = ('created_at',)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'target_type', 'target_id', 'created_at')
    list_filter = ('target_type',)
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)
