from django.urls import path
from .views import ServiceListView, ServiceDetailView
from references.views import ServiceCategoriesView

urlpatterns = [
    path('', ServiceListView.as_view(), name='service-list'),
    # Алиас: фронт также обращается к /api/services/categories/
    path('categories/', ServiceCategoriesView.as_view(), name='service-categories-alias'),
    path('<int:pk>/', ServiceDetailView.as_view(), name='service-detail'),
]
