from django.urls import path
from .views import ReviewListCreateView, ReviewDetailView, ReviewReplyView

urlpatterns = [
    path('', ReviewListCreateView.as_view(), name='review-list-create'),
    path('<int:pk>/', ReviewDetailView.as_view(), name='review-detail'),
    path('<int:pk>/reply/', ReviewReplyView.as_view(), name='review-reply'),
]
