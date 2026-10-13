import threading
from unittest import mock

import httpx
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from openai import APITimeoutError
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from chat import views
from chat.models import AIMessage
from users.models import User

SEND_URL = '/api/chat/ai/send/'
REPLY = '{"content": "Обратитесь к терапевту.", "recommend": false, "entity_types": [], "specializations": []}'


def openai_returning(content=REPLY, on_call=None):
    """Подменённый класс OpenAI: create() отдаёт готовый ответ модели."""
    def create(**kwargs):
        if on_call:
            on_call()
        choice = mock.Mock()
        choice.message.content = content
        return mock.Mock(choices=[choice])

    client = mock.Mock()
    client.chat.completions.create.side_effect = create
    return mock.Mock(return_value=client)


class AIChatSendProtectionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='ai-patient@example.com', password='password123', first_name='Ivan', role=User.Role.PATIENT,
        )
        self.client.force_authenticate(user=self.user)

    def test_reply_is_saved_with_the_question(self):
        with mock.patch.object(views, 'OpenAI', openai_returning()):
            response = self.client.post(SEND_URL, {'message': 'Болит горло'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], 'Обратитесь к терапевту.')
        self.assertEqual(
            list(AIMessage.objects.filter(user=self.user).values_list('role', flat=True).order_by('created_at')),
            [AIMessage.Role.USER, AIMessage.Role.ASSISTANT],
        )

    def test_openai_call_has_timeout_and_no_retries(self):
        openai_cls = openai_returning()
        with mock.patch.object(views, 'OpenAI', openai_cls):
            self.client.post(SEND_URL, {'message': 'Болит горло'}, format='json')

        kwargs = openai_cls.call_args.kwargs
        self.assertLess(kwargs['timeout'], 15)  # фронт ждёт ответа 15 с
        self.assertEqual(kwargs['max_retries'], 0)

    def test_openai_failure_returns_503_and_drops_the_question(self):
        failing = mock.Mock()
        failing.chat.completions.create.side_effect = APITimeoutError(
            request=httpx.Request('POST', 'https://api.openai.com/v1/chat/completions'),
        )
        with mock.patch.object(views, 'OpenAI', mock.Mock(return_value=failing)):
            response = self.client.post(SEND_URL, {'message': 'Болит горло'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['detail'], views.AI_FAILED_MESSAGE)
        # Вопрос без ответа не остаётся: повтор не задвоит его в истории.
        self.assertFalse(AIMessage.objects.filter(user=self.user).exists())

    def test_busy_when_all_slots_are_taken(self):
        openai_cls = openai_returning()
        with mock.patch.object(views, '_ai_slots', threading.BoundedSemaphore(1)) as slots, \
                mock.patch.object(views, 'OpenAI', openai_cls):
            slots.acquire()  # единственный слот занят другим вопросом
            response = self.client.post(SEND_URL, {'message': 'Болит горло'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['detail'], views.AI_BUSY_MESSAGE)
        openai_cls.assert_not_called()
        self.assertFalse(AIMessage.objects.exists())

    def test_slot_is_released_after_an_error(self):
        failing = mock.Mock()
        failing.chat.completions.create.side_effect = APITimeoutError(
            request=httpx.Request('POST', 'https://api.openai.com/v1/chat/completions'),
        )
        with mock.patch.object(views, '_ai_slots', threading.BoundedSemaphore(1)):
            with mock.patch.object(views, 'OpenAI', mock.Mock(return_value=failing)):
                self.client.post(SEND_URL, {'message': 'Раз'}, format='json')
            with mock.patch.object(views, 'OpenAI', openai_returning()):
                response = self.client.post(SEND_URL, {'message': 'Два'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_messages_per_user_are_rate_limited(self):
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'ai_chat': '2/min'}), \
                mock.patch.object(views, 'OpenAI', openai_returning()):
            codes = [
                self.client.post(SEND_URL, {'message': f'Вопрос {i}'}, format='json').status_code
                for i in range(3)
            ]

        self.assertEqual(codes, [201, 201, 429])

    def test_too_long_message_is_rejected(self):
        with mock.patch.object(views, 'OpenAI', openai_returning()) as openai_cls:
            response = self.client.post(SEND_URL, {'message': 'а' * 2001}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        openai_cls.assert_not_called()


class AIChatSendConnectionTests(TransactionTestCase):
    """Пока ждём OpenAI, соединение с БД отдано — иначе ~100 одновременных
    вопросов съедали все соединения Postgres и падал весь сайт."""

    def test_db_connection_is_released_while_waiting_for_openai(self):
        cache.clear()
        user = User.objects.create_user(
            email='ai-conn@example.com', password='password123', first_name='Ivan', role=User.Role.PATIENT,
        )
        client = APIClient()
        client.force_authenticate(user=user)
        order = []

        # Тестовая SQLite в памяти игнорирует close() (иначе пропала бы база),
        # поэтому проверяем порядок: соединение отдаётся ДО вызова OpenAI.
        # Эффект на Postgres проверен нагрузкой на стенде.
        with mock.patch.object(connection, 'close', side_effect=lambda: order.append('db-close')), \
                mock.patch.object(views, 'OpenAI', openai_returning(on_call=lambda: order.append('openai'))):
            response = client.post(SEND_URL, {'message': 'Болит горло'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(order[:2], ['db-close', 'openai'])
        self.assertEqual(AIMessage.objects.filter(user=user).count(), 2)
