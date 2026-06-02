from django.contrib import admin
from .models import BlogCategory, BlogPost


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'date', 'is_featured', 'is_published', 'created_at')
    list_filter = ('is_published', 'is_featured', 'category')
    search_fields = ('title', 'description', 'content')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'date'
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Основное', {'fields': ('title', 'slug', 'category', 'date', 'image')}),
        ('Содержание', {'fields': ('description', 'content')}),
        ('Настройки', {'fields': ('is_featured', 'is_published')}),
        ('Даты', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
