"""Приём и верификация вебхуков LiveKit + диспетчеризация событий в services."""
import logging

from . import services
from .client import get_webhook_receiver

logger = logging.getLogger(__name__)

_HANDLERS = {
    'participant_joined': services.handle_participant_joined,
    'participant_left': services.handle_participant_left,
    'room_finished': services.handle_room_finished,
    'egress_started': services.handle_egress_updated,
    'egress_updated': services.handle_egress_updated,
    'egress_ended': services.handle_egress_updated,
}


class InvalidWebhookSignature(Exception):
    """Подпись вебхука LiveKit не прошла проверку."""


def verify_and_parse(body: bytes, auth_header: str):
    """Проверить подпись (JWT в заголовке Authorization) и распарсить тело события.

    Использует WebhookReceiver из livekit-api, который сверяет JWT, подписанный
    LIVEKIT_API_KEY/LIVEKIT_API_SECRET, и хэш тела запроса — тем самым гарантирует,
    что запрос действительно пришёл от LiveKit и тело не было подменено.
    """
    receiver = get_webhook_receiver()
    try:
        return receiver.receive(body.decode('utf-8'), auth_header or '')
    except Exception as exc:
        logger.warning('LiveKit webhook: неверная подпись/тело запроса: %s', exc)
        raise InvalidWebhookSignature(str(exc)) from exc


def dispatch(event) -> None:
    handler = _HANDLERS.get(event.event)
    if handler is None:
        logger.info('LiveKit webhook: событие "%s" не обрабатывается, пропущено', event.event)
        return
    logger.info('LiveKit webhook: обработка события "%s"', event.event)
    handler(event)
