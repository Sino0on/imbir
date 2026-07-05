import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import ChatRoom, ChatMessage

logger = logging.getLogger(__name__)


def get_or_create_room(user_a, user_b):
    """Находит существующую личную комнату между двумя пользователями или создаёт новую."""
    room = (
        ChatRoom.objects
        .filter(participants=user_a)
        .filter(participants=user_b)
        .first()
    )
    if not room:
        room = ChatRoom.objects.create()
        room.participants.add(user_a, user_b)
    return room


def send_system_message(room, content):
    """
    Создаёт системное сообщение (sender=None) в комнате и рассылает его
    подключённым по WebSocket участникам. Фронт отображает такие сообщения
    как уведомление. Рассылка best-effort: если канальный слой недоступен,
    сообщение всё равно сохраняется и придёт при следующей загрузке истории.
    """
    msg = ChatMessage.objects.create(room=room, sender=None, content=content)

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'chat_{room.id}',
            {
                'type': 'chat_message',
                'id': msg.id,
                'sender_id': None,
                'sender_name': None,
                'content': content,
                'created_at': msg.created_at.isoformat(),
            },
        )
    except Exception:
        logger.exception('Не удалось разослать системное сообщение в комнату %s', room.id)

    return msg
