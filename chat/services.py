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


def mark_room_read(room_id, reader):
    """
    Помечает прочитанными входящие сообщения комнаты для reader и рассылает
    участникам событие «прочитано» (у отправителя галочки становятся зелёными,
    у самого reader обновляются счётчики непрочитанного). Рассылка best-effort,
    как и у системных сообщений. Возвращает id помеченных сообщений.
    """
    unread = ChatMessage.objects.filter(room_id=room_id, is_read=False).exclude(sender=reader)
    message_ids = list(unread.values_list('id', flat=True))
    if not message_ids:
        return []
    ChatMessage.objects.filter(pk__in=message_ids).update(is_read=True)

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'chat_{room_id}',
            {
                'type': 'chat_messages_read',
                'message_ids': message_ids,
                'reader_id': reader.id,
            },
        )
    except Exception:
        logger.exception('Не удалось разослать отметку о прочтении в комнату %s', room_id)

    return message_ids
