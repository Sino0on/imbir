from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),

    # OpenAPI schema + UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API
    path('api/auth/', include('users.urls')),
    path('api/doctors/', include('doctors.urls')),
    path('api/clinics/', include('clinics.urls')),
    path('api/services/', include('services.urls')),
    path('api/references/', include('references.urls')),
    path('api/appointments/', include('appointments.urls')),
    path('api/doctor/', include('doctor.urls')),
    path('api/reviews/', include('reviews.urls')),
    path('api/profile/', include('profile.urls')),
    path('api/clinic/', include('clinic.urls')),
    path('api/blog/', include('blog.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/upload/', include('upload.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
