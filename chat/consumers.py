import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


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
            'id': event['id'],
            'sender': sender,
            'content': event['content'],
            'created_at': event['created_at'],
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
