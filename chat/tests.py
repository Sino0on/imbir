from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from users.models import User
from chat.models import ChatRoom, ChatMessage


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
