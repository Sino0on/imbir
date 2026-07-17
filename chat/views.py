from django.conf import settings
from django.db.models import Q
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from openai import OpenAI
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer

from .models import ChatRoom, ChatMessage, AIMessage
from .serializers import (
    ChatRoomSerializer, ChatMessageSerializer, CreateRoomSerializer,
    AIMessageSerializer, SendAIMessageSerializer,
)

AI_SYSTEM_PROMPT = (
    'Ты опытный врач-терапевт. Отвечай на вопросы пользователя о здоровье, симптомах и лечении '
    'на русском языке. Давай профессиональные, но понятные советы. '
    'Если ситуация требует срочной медицинской помощи — обязательно скажи об этом. '
    'Не ставь окончательных диагнозов — рекомендуй обратиться к специалисту при необходимости.'
)

# Инструкция про формат ответа и когда рекомендовать врачей/клиники/услуги.
AI_RECOMMENDATION_INSTRUCTIONS = (
    'Всегда отвечай СТРОГО в формате JSON со следующими полями:\n'
    '- "content" (string): твой ответ пользователю на русском языке.\n'
    '- "recommend" (boolean): true ТОЛЬКО когда из разговора уже понятна '
    'потребность пользователя и уместно порекомендовать специалиста, клинику или услугу. '
    'На приветствия, уточняющие и общие вопросы ставь false — не рекомендуй на каждое сообщение.\n'
    '- "entity_types" (array of strings): какие типы рекомендовать, подмножество '
    'из ["doctors", "clinics", "services"]. Пустой массив, если recommend=false.\n'
    '- "tags" (array of strings): подходящие теги СТРОГО из списка ниже, дословно. '
    'Не придумывай новых тегов. Пустой массив, если recommend=false.\n'
    'Если подходящих тегов в списке нет — ставь recommend=false.\n'
    'Доступные теги: {tags}'
)
MAX_HISTORY = 20


def _build_system_messages():
    from references.models import Tag
    tag_names = list(Tag.objects.values_list('name', flat=True))
    tags_str = ', '.join(tag_names) if tag_names else '(список пуст)'
    return [
        {'role': 'system', 'content': AI_SYSTEM_PROMPT},
        {'role': 'system', 'content': AI_RECOMMENDATION_INSTRUCTIONS.format(tags=tags_str)},
    ]


# ── Комнаты ──────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        responses={200: ChatRoomSerializer(many=True)},
        tags=['Chat Rooms'],
        summary='Список комнат чата'
    ),
    post=extend_schema(
        request=CreateRoomSerializer,
        responses={201: ChatRoomSerializer},
        tags=['Chat Rooms'],
        summary='Создать или получить комнату чата с пользователем'
    )
)
class RoomListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        rooms = ChatRoom.objects.filter(participants=request.user).prefetch_related('participants', 'messages')
        return Response(ChatRoomSerializer(rooms, many=True).data)

    def post(self, request):
        serializer = CreateRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        other_id = serializer.validated_data['user_id']

        if other_id == request.user.id:
            return Response({'detail': 'Нельзя создать чат с самим собой.'}, status=400)

        from users.models import User
        try:
            other = User.objects.get(pk=other_id)
        except User.DoesNotExist:
            return Response({'detail': 'Пользователь не найден.'}, status=404)

        # Ищем существующую комнату между двумя пользователями
        room = (
            ChatRoom.objects
            .filter(participants=request.user)
            .filter(participants=other)
            .first()
        )
        if not room:
            room = ChatRoom.objects.create()
            room.participants.add(request.user, other)

        return Response(ChatRoomSerializer(room).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        responses={200: ChatMessageSerializer(many=True)},
        tags=['Chat Rooms'],
        summary='Список сообщений в комнате'
    )
)
class RoomMessagesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, pk):
        room = ChatRoom.objects.filter(pk=pk, participants=request.user).first()
        if not room:
            return Response({'detail': 'Комната не найдена.'}, status=404)
        messages = room.messages.select_related('sender').all()
        # Помечаем входящие как прочитанные
        messages.exclude(sender=request.user).filter(is_read=False).update(is_read=True)
        return Response(ChatMessageSerializer(messages, many=True).data)


# ── ИИ чат (комната 0) ───────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        responses={200: AIMessageSerializer(many=True)},
        tags=['AI Chat'],
        summary='История сообщений с ИИ'
    ),
    delete=extend_schema(
        responses={204: None},
        tags=['AI Chat'],
        summary='Очистить историю сообщений с ИИ'
    )
)
class AIChatHistoryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        messages = AIMessage.objects.filter(user=request.user)
        return Response(AIMessageSerializer(messages, many=True, context={'request': request}).data)

    def delete(self, request):
        AIMessage.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    post=extend_schema(
        request=SendAIMessageSerializer,
        responses={201: AIMessageSerializer},
        tags=['AI Chat'],
        summary='Отправить сообщение ИИ-врачу'
    )
)
class AIChatSendView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = SendAIMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_text = serializer.validated_data['message']

        AIMessage.objects.create(user=request.user, role=AIMessage.Role.USER, content=user_text)

        history = list(
            AIMessage.objects.filter(user=request.user).order_by('-created_at')[:MAX_HISTORY]
        )
        openai_messages = _build_system_messages()
        openai_messages += [{'role': m.role, 'content': m.content} for m in reversed(history)]

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=openai_messages,
            response_format={'type': 'json_object'},
        )
        raw = completion.choices[0].message.content

        content, recommend, entity_types, tags = self._parse_ai_reply(raw)

        recommendations_ids = {}
        if recommend and tags:
            from .recommendations import query_recommendations
            recommendations_ids = query_recommendations(tags, entity_types)

        ai_message = AIMessage.objects.create(
            user=request.user,
            role=AIMessage.Role.ASSISTANT,
            content=content,
            recommendations=recommendations_ids,
        )
        return Response(
            AIMessageSerializer(ai_message, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _parse_ai_reply(raw):
        """Разбирает JSON-ответ модели. При сбое — трактуем весь текст как content без рекомендаций."""
        import json
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return (raw or '').strip(), False, [], []

        content = (data.get('content') or '').strip() or (raw or '').strip()
        recommend = bool(data.get('recommend'))
        entity_types = data.get('entity_types') or []
        tags = data.get('tags') or []
        if not isinstance(entity_types, list):
            entity_types = []
        if not isinstance(tags, list):
            tags = []
        # оставляем только валидные типы сущностей
        entity_types = [t for t in entity_types if t in ('doctors', 'clinics', 'services')]
        return content, recommend, entity_types, tags


@extend_schema(
    responses={200: inline_serializer('UnreadCountResponse', fields={'unread_count': serializers.IntegerField()})},
    tags=['Chat Rooms'],
    summary='Количество непрочитанных сообщений'
)
class UnreadMessagesCountView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        unread_count = ChatMessage.objects.filter(
            room__participants=request.user,
            is_read=False
        ).exclude(
            sender=request.user
        ).count()
        return Response({'unread_count': unread_count})

