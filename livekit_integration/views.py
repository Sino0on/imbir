"""View-слой LiveKit: тонкие обёртки, вся логика — в services.py / webhooks.py."""
import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments.models import Appointment
from . import services
from .serializers import LiveKitTokenResponseSerializer
from .webhooks import InvalidWebhookSignature, dispatch, verify_and_parse

logger = logging.getLogger(__name__)


class LiveKitTokenView(APIView):
    """GET /api/livekit/token/?consultation_id={id}

    Требует JWT-аутентификацию (глобальная настройка DRF). Все проверки участия/
    оплаты/окна времени — в permissions.ensure_can_join, вызываемой из services.
    """
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='consultation_id',
                type=int,
                location=OpenApiParameter.QUERY,
                required=True,
                description='ID консультации (Appointment)',
            ),
        ],
        tags=['LiveKit'],
        summary='Получить токен подключения к видео-консультации',
        description=(
            'Выдаёт JWT для подключения к комнате LiveKit. Доступно только врачу '
            'и пациенту этой консультации, при оплаченной и не отменённой записи, '
            'в пределах окна ±LIVEKIT_JOIN_WINDOW_MINUTES от времени начала.'
        ),
        responses={200: LiveKitTokenResponseSerializer},
    )
    def get(self, request):
        consultation_id = request.query_params.get('consultation_id')
        if not consultation_id:
            raise ValidationError({'consultation_id': 'Обязательный параметр.'})

        appointment = get_object_or_404(
            Appointment.objects.select_related('patient', 'doctor__user'),
            pk=consultation_id,
        )
        data = services.generate_token_for_participant(appointment, request.user)
        return Response(data)


@method_decorator(csrf_exempt, name='dispatch')
class LiveKitWebhookView(View):
    """POST /api/livekit/webhook

    Обычный Django View (не DRF): LiveKit шлёт Content-Type: application/webhook+json,
    и подпись проверяется по сырому телу запроса, поэтому DRF-парсеры здесь не нужны.
    Аутентификация запроса — сама подпись вебхука (verify_and_parse), а не JWT.
    """

    def post(self, request, *args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        try:
            event = verify_and_parse(request.body, auth_header)
        except InvalidWebhookSignature:
            return HttpResponse(status=401)

        try:
            dispatch(event)
        except Exception:
            logger.exception(
                'LiveKit webhook: ошибка обработки события "%s"', getattr(event, 'event', '?'),
            )
            # Не 2xx — LiveKit повторит доставку события позже.
            return HttpResponse(status=500)

        return HttpResponse(status=200)
