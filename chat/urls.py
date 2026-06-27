from django.urls import path
from .views import RoomListCreateView, RoomMessagesView, AIChatHistoryView, AIChatSendView

urlpatterns = [
    # Комнаты
    path('rooms/', RoomListCreateView.as_view()),
    path('rooms/<int:pk>/messages/', RoomMessagesView.as_view()),

    # ИИ чат (комната 0)
    path('ai/', AIChatHistoryView.as_view()),
    path('ai/send/', AIChatSendView.as_view()),
]
