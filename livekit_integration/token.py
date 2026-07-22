"""Генерация LiveKit access token (JWT) для подключения к комнате."""
import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from livekit import api

from .client import LiveKitConfigError, is_configured

logger = logging.getLogger(__name__)

DOCTOR_ROLE = 'doctor'
PATIENT_ROLE = 'patient'


def build_identity(role: str, user_id: int) -> str:
    """identity участника в комнате: '<role>-<user_id>', например 'doctor-42'."""
    return f'{role}-{user_id}'


def role_from_identity(identity: str) -> Optional[str]:
    if identity.startswith(f'{DOCTOR_ROLE}-'):
        return DOCTOR_ROLE
    if identity.startswith(f'{PATIENT_ROLE}-'):
        return PATIENT_ROLE
    return None


def generate_access_token(
    *,
    identity: str,
    name: str,
    room: str,
    ttl_minutes: Optional[int] = None,
    can_publish: bool = True,
    can_subscribe: bool = True,
) -> str:
    """Сгенерировать подписанный JWT с правами на подключение к конкретной комнате.

    Токен ограничен по времени жизни (ttl) и даёт доступ ровно к одной комнате
    (room_join=True, room=<room>) — это и есть "безопасный токен подключения".
    """
    if not is_configured():
        raise LiveKitConfigError(
            'LiveKit не сконфигурирован: заполните LIVEKIT_URL, LIVEKIT_API_KEY, '
            'LIVEKIT_API_SECRET в .env'
        )

    ttl = ttl_minutes if ttl_minutes is not None else settings.LIVEKIT_TOKEN_TTL_MINUTES

    access_token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(name)
        .with_ttl(timedelta(minutes=ttl))
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
            can_publish_data=True,
        ))
    )
    jwt = access_token.to_jwt()
    logger.info('LiveKit: сгенерирован access token identity=%s room=%s ttl=%sm', identity, room, ttl)
    return jwt
