import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get('user')
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.group_name = f'chat_{self.room_id}'

        # Проверяем что пользователь является участником комнаты
        is_member = await self.check_membership(user, self.room_id)
        if not is_member:
            await self.close(code=4003)
            return

        self.user = user
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, AttributeError):
            return

        msg_type = data.get('type', 'message')

        if msg_type == 'typing':
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'typing_status',
                    'sender_channel': self.channel_name,
                    'user_id': self.user.id,
                    'user_name': self.user.full_name,
                    'is_typing': bool(data.get('is_typing', False)),
                },
            )
            return

        if msg_type == 'edit':
            content = data.get('content', '').strip()
            message = await self.edit_message(data.get('message_id'), content)
            if message:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'chat_message_edited',
                        **message,
                    },
                )
            return

        if msg_type == 'delete':
            raw_ids = data.get('message_ids', data.get('message_id'))
            message_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
            deleted_ids = await self.delete_messages(message_ids)
            if deleted_ids:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'chat_messages_deleted',
                        'message_ids': deleted_ids,
                    },
                )
            return

        content = data.get('content', '').strip()
        if not content:
            return

        message = await self.save_message(self.user, self.room_id, content)

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'chat_message',
                'id': message['id'],
                'sender_id': self.user.id,
                'sender_name': self.user.full_name,
                'content': content,
                'created_at': message['created_at'],
            },
        )

    async def chat_message(self, event):
        sender = None
        if event.get('sender_id') is not None:
            sender = {'id': event['sender_id'], 'full_name': event['sender_name']}
        await self.send(text_data=json.dumps({
            'type': 'message',
            'id': event['id'],
            'sender': sender,
            'content': event['content'],
            'created_at': event['created_at'],
        }))

    async def chat_message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'id': event['id'],
            'content': event['content'],
            'edited_at': event['edited_at'],
        }))

    async def chat_messages_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'messages_deleted',
            'message_ids': event['message_ids'],
        }))

    async def typing_status(self, event):
        # не отправляем обратно тому, кто печатает
        if event['sender_channel'] == self.channel_name:
            return
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user_id': event['user_id'],
            'user_name': event['user_name'],
            'is_typing': event['is_typing'],
        }))

    @database_sync_to_async
    def check_membership(self, user, room_id):
        from .models import ChatRoom
        return ChatRoom.objects.filter(pk=room_id, participants=user).exists()

    @database_sync_to_async
    def save_message(self, user, room_id, content):
        from .models import ChatRoom, ChatMessage
        room = ChatRoom.objects.get(pk=room_id)
        msg = ChatMessage.objects.create(room=room, sender=user, content=content)
        return {'id': msg.id, 'created_at': msg.created_at.isoformat()}

    @database_sync_to_async
    def edit_message(self, message_id, content):
        from .models import ChatMessage

        if not content or not str(message_id).isdigit():
            return None
        message = ChatMessage.objects.filter(
            pk=int(message_id), room_id=self.room_id, sender=self.user,
            is_deleted=False,
        ).first()
        if not message:
            return None
        message.content = content
        message.edited_at = timezone.now()
        message.save(update_fields=('content', 'edited_at'))
        return {
            'id': message.id,
            'content': message.content,
            'edited_at': message.edited_at.isoformat(),
        }

    @database_sync_to_async
    def delete_messages(self, message_ids):
        from .models import ChatMessage

        ids = {
            int(message_id) for message_id in message_ids
            if str(message_id).isdigit()
        }
        if not ids:
            return []
        messages = ChatMessage.objects.filter(
            pk__in=ids, room_id=self.room_id, sender=self.user,
            is_deleted=False,
        )
        deleted_ids = list(messages.values_list('id', flat=True))
        messages.update(is_deleted=True, content='', edited_at=None)
        return deleted_ids
