from django.contrib import admin
from .models import Interview


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'doctor', 'video_url', 'priority')
    list_filter = ('priority',)
    search_fields = ('title', 'doctor__user__first_name', 'doctor__user__last_name')
