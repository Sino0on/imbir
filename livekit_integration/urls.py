from django.urls import path

from .views import LiveKitTokenView, LiveKitWebhookView

urlpatterns = [
    path('token/', LiveKitTokenView.as_view(), name='livekit-token'),
    path('webhook', LiveKitWebhookView.as_view(), name='livekit-webhook'),
]
