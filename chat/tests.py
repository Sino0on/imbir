import asyncio

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from users.models import User, ClinicProfile, DoctorProfile
from chat.models import ChatRoom, ChatMessage
from chat.consumers import ChatConsumer
from chat.recommendations import query_recommendations, serialize_recommendations
from references.models import Specialization
from services.models import Service


class UnreadCountTests(APITestCase):
    def setUp(self):
        # Create users
        self.user_1 = User.objects.create_user(
            email='user1@example.com', password='password123', first_name='Ivan', role=User.Role.DOCTOR
        )
        self.user_2 = User.objects.create_user(
            email='user2@example.com', password='password123', first_name='Petr', role=User.Role.PATIENT
        )

        # Create room
        self.room = ChatRoom.objects.create()
        self.room.participants.add(self.user_1, self.user_2)

        self.unread_url = '/api/chat/rooms/unread-count/'
        self.messages_url = f'/api/chat/rooms/{self.room.pk}/messages/'

    def test_unread_count_unauthorized(self):
        response = self.client.get(self.unread_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unread_count_lifecycle(self):
        # Authenticate user 1
        self.client.force_authenticate(user=self.user_1)

        # 1. Init: 0 unread messages
        response = self.client.get(self.unread_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread_count'], 0)

        # 2. Sent by user 1: should still be 0 unread for user 1
        ChatMessage.objects.create(room=self.room, sender=self.user_1, content='Hello')
        response = self.client.get(self.unread_url)
        self.assertEqual(response.data['unread_count'], 0)

        # 3. Sent by user 2: user 1 should now have 1 unread message
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='Reply from 2')
        response = self.client.get(self.unread_url)
        self.assertEqual(response.data['unread_count'], 1)

        # 4. Sent another by user 2: user 1 should now have 2 unread messages
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='Another reply')
        response = self.client.get(self.unread_url)
        self.assertEqual(response.data['unread_count'], 2)

        # 5. Retrieve messages (this action marks incoming messages as read)
        msg_response = self.client.get(self.messages_url)
        self.assertEqual(msg_response.status_code, status.HTTP_200_OK)

        # 6. Unread count should go back to 0
        response = self.client.get(self.unread_url)
        self.assertEqual(response.data['unread_count'], 0)


class ChatMessageModerationTests(APITestCase):
    def setUp(self):
        self.user_1 = User.objects.create_user(
            email='edit1@example.com', password='password123', first_name='Ivan', role=User.Role.DOCTOR
        )
        self.user_2 = User.objects.create_user(
            email='edit2@example.com', password='password123', first_name='Petr', role=User.Role.PATIENT
        )
        self.room = ChatRoom.objects.create()
        self.room.participants.add(self.user_1, self.user_2)
        self.client.force_authenticate(user=self.user_1)

    def test_history_exposes_edit_and_delete_state(self):
        message = ChatMessage.objects.create(
            room=self.room, sender=self.user_1, content='Original'
        )
        message.content = 'Updated'
        message.edited_at = message.created_at
        message.is_deleted = True
        message.save()

        response = self.client.get(f'/api/chat/rooms/{self.room.pk}/messages/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['content'], 'Updated')
        self.assertTrue(response.data[0]['edited_at'])
        self.assertTrue(response.data[0]['is_deleted'])


class RoomUnreadCountTests(APITestCase):
    """Счётчик непрочитанного по комнате и общий — без своих и удалённых."""

    def setUp(self):
        self.user_1 = User.objects.create_user(
            email='room1@example.com', password='password123', first_name='Ivan', role=User.Role.DOCTOR
        )
        self.user_2 = User.objects.create_user(
            email='room2@example.com', password='password123', first_name='Petr', role=User.Role.PATIENT
        )
        self.room = ChatRoom.objects.create()
        self.room.participants.add(self.user_1, self.user_2)
        self.client.force_authenticate(user=self.user_1)

    def test_room_list_exposes_unread_count(self):
        ChatMessage.objects.create(room=self.room, sender=self.user_1, content='own')
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='unread 1')
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='unread 2')
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='read', is_read=True)
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='', is_deleted=True)

        response = self.client.get('/api/chat/rooms/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['unread_count'], 2)

        # После открытия комнаты счётчик обнуляется
        self.client.get(f'/api/chat/rooms/{self.room.pk}/messages/')
        response = self.client.get('/api/chat/rooms/')
        self.assertEqual(response.data[0]['unread_count'], 0)

    def test_unread_count_endpoint_skips_deleted_messages(self):
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='unread')
        ChatMessage.objects.create(room=self.room, sender=self.user_2, content='', is_deleted=True)

        response = self.client.get('/api/chat/rooms/unread-count/')

        self.assertEqual(response.data['unread_count'], 1)


class ChatReadReceiptsTests(TransactionTestCase):
    """Отметки о прочтении: новое сообщение несёт is_read, прочтение рассылается в сокет."""

    def setUp(self):
        self.sender = User.objects.create_user(
            email='rr1@example.com', password='password123', first_name='Ivan', role=User.Role.PATIENT
        )
        self.reader = User.objects.create_user(
            email='rr2@example.com', password='password123', first_name='Petr', role=User.Role.DOCTOR
        )
        self.room = ChatRoom.objects.create()
        self.room.participants.add(self.sender, self.reader)

    def _communicator(self, user, receipts=True):
        path = f'/ws/chat/{self.room.pk}/' + ('?receipts=1' if receipts else '')
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), path)
        communicator.scope['user'] = user
        communicator.scope['url_route'] = {'kwargs': {'room_id': str(self.room.pk)}}
        return communicator

    def test_ws_message_carries_is_read_and_read_frame_is_broadcast(self):
        async def scenario():
            sender_ws = self._communicator(self.sender)
            reader_ws = self._communicator(self.reader)
            self.assertTrue((await sender_ws.connect())[0])
            self.assertTrue((await reader_ws.connect())[0])

            await sender_ws.send_json_to({'content': 'Здравствуйте'})
            echo = await sender_ws.receive_json_from()
            incoming = await reader_ws.receive_json_from()
            self.assertEqual(echo['type'], 'message')
            self.assertIs(echo['is_read'], False)
            self.assertIs(incoming['is_read'], False)

            # Получатель держит комнату открытой — помечает входящее прочитанным
            await reader_ws.send_json_to({'type': 'read'})
            read_for_sender = await sender_ws.receive_json_from()
            read_for_reader = await reader_ws.receive_json_from()

            await sender_ws.disconnect()
            await reader_ws.disconnect()
            return echo, read_for_sender, read_for_reader

        echo, read_for_sender, read_for_reader = async_to_sync(scenario)()

        self.assertEqual(read_for_sender, {
            'type': 'messages_read', 'message_ids': [echo['id']], 'reader_id': self.reader.id,
        })
        self.assertEqual(read_for_reader['type'], 'messages_read')
        self.assertTrue(ChatMessage.objects.get(pk=echo['id']).is_read)

    def test_old_client_does_not_get_read_frame(self):
        # Старый фронт без ?receipts=1 незнакомый кадр рисует как пустое сообщение
        async def scenario():
            old_sender_ws = self._communicator(self.sender, receipts=False)
            reader_ws = self._communicator(self.reader)
            self.assertTrue((await old_sender_ws.connect())[0])
            self.assertTrue((await reader_ws.connect())[0])

            await old_sender_ws.send_json_to({'content': 'Здравствуйте'})
            await old_sender_ws.receive_json_from()
            await reader_ws.receive_json_from()

            await reader_ws.send_json_to({'type': 'read'})
            read_for_reader = await reader_ws.receive_json_from()
            nothing_for_old = await old_sender_ws.receive_nothing(timeout=0.5)

            await old_sender_ws.disconnect()
            await reader_ws.disconnect()
            return read_for_reader, nothing_for_old

        read_for_reader, nothing_for_old = async_to_sync(scenario)()

        self.assertEqual(read_for_reader['type'], 'messages_read')
        self.assertTrue(nothing_for_old)

    def test_history_request_broadcasts_read_event(self):
        message = ChatMessage.objects.create(room=self.room, sender=self.sender, content='Hi')
        channel_layer = get_channel_layer()
        channel_name = async_to_sync(channel_layer.new_channel)()
        async_to_sync(channel_layer.group_add)(f'chat_{self.room.pk}', channel_name)

        client = APIClient()
        client.force_authenticate(user=self.reader)
        response = client.get(f'/api/chat/rooms/{self.room.pk}/messages/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        async def receive_event():
            return await asyncio.wait_for(channel_layer.receive(channel_name), timeout=2)

        event = async_to_sync(receive_event)()
        self.assertEqual(event['type'], 'chat_messages_read')
        self.assertEqual(event['message_ids'], [message.id])
        self.assertEqual(event['reader_id'], self.reader.id)


class AIRecommendationsVisibilityTests(APITestCase):
    """ИИ-ассистент не рекомендует снятых с публикации врачей/клиники и их услуги."""

    def setUp(self):
        self.spec = Specialization.objects.create(name='Кардиолог')

    def _clinic(self, email, is_published=True):
        user = User.objects.create_user(email=email, password='password123', role=User.Role.CLINIC)
        clinic = ClinicProfile.objects.create(user=user, name=email, is_published=is_published)
        clinic.primary_specializations.add(self.spec)
        return clinic

    def _doctor(self, email, is_published=True):
        user = User.objects.create_user(
            email=email, password='password123', first_name='Doc', role=User.Role.DOCTOR
        )
        doctor = DoctorProfile.objects.create(user=user, is_published=is_published)
        doctor.primary_specializations.add(self.spec)
        return doctor

    def test_unpublished_entities_are_not_recommended(self):
        visible_clinic = self._clinic('visible@clinic.kg')
        hidden_clinic = self._clinic('hidden@clinic.kg', is_published=False)
        visible_doctor = self._doctor('visible@doc.kg')
        self._doctor('hidden@doc.kg', is_published=False)
        visible_service = Service.objects.create(name='ЭКГ', category='Диагностика', clinic=visible_clinic)
        hidden_service = Service.objects.create(name='ЭКГ', category='Диагностика', clinic=hidden_clinic)
        visible_service.doctors.add(visible_doctor)
        hidden_service.doctors.add(visible_doctor)

        result = query_recommendations(['Кардиолог'], ['doctors', 'clinics', 'services'])

        self.assertEqual(result['doctors'], [visible_doctor.pk])
        self.assertEqual(result['clinics'], [visible_clinic.pk])
        self.assertEqual(result['services'], [visible_service.pk])

    def test_cards_hide_entities_unpublished_after_answer(self):
        clinic = self._clinic('later@clinic.kg')
        doctor = self._doctor('later@doc.kg')
        service = Service.objects.create(name='ЭКГ', category='Диагностика', clinic=clinic)
        stored = {'doctors': [doctor.pk], 'clinics': [clinic.pk], 'services': [service.pk]}

        clinic.is_published = False
        clinic.save(update_fields=['is_published'])
        doctor.is_published = False
        doctor.save(update_fields=['is_published'])

        cards = serialize_recommendations(stored, None)

        self.assertEqual(cards, {'doctors': [], 'clinics': [], 'services': []})
