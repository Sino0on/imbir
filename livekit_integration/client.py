"""
Тонкая обёртка над LiveKit Server SDK (livekit-api).

LiveKit Server SDK асинхронный (aiohttp), а этот проект — синхронный Django/DRF.
Все обращения к LiveKit REST API идут через run_sync(), которая поднимает
клиента, выполняет переданную корутину и корректно его закрывает.

Работа с LiveKit нигде за пределами этого модуля и services.py не производится —
во View LiveKit-клиент напрямую не импортируется.
"""
import logging
from typing import Awaitable, Callable, TypeVar

from asgiref.sync import async_to_sync
from django.conf import settings
from livekit import api

logger = logging.getLogger(__name__)

T = TypeVar('T')


class LiveKitConfigError(RuntimeError):
    """LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET не заданы в окружении."""


def is_configured() -> bool:
    return bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)


def _ensure_configured() -> None:
    if not is_configured():
        raise LiveKitConfigError(
            'LiveKit не сконфигурирован: заполните LIVEKIT_URL, LIVEKIT_API_KEY, '
            'LIVEKIT_API_SECRET в .env'
        )


def run_sync(call: Callable[['api.LiveKitAPI'], Awaitable[T]]) -> T:
    """Синхронно выполнить вызов к LiveKit Server API.

    call — функция, принимающая LiveKitAPI-клиент и возвращающая корутину, например:
        run_sync(lambda c: c.room.create_room(api.CreateRoomRequest(name=name)))
    """
    _ensure_configured()

    async def _runner() -> T:
        client = api.LiveKitAPI(
            settings.LIVEKIT_URL,
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET,
        )
        try:
            return await call(client)
        finally:
            await client.aclose()

    try:
        return async_to_sync(_runner)()
    except Exception:
        logger.exception('Ошибка запроса к LiveKit Server API')
        raise


def get_token_verifier() -> 'api.TokenVerifier':
    _ensure_configured()
    return api.TokenVerifier(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)


def get_webhook_receiver() -> 'api.WebhookReceiver':
    return api.WebhookReceiver(get_token_verifier())
