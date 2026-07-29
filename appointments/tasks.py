"""
Celery-задачи по консультациям.

generate_consultation_summary ставится в очередь из
livekit_integration.services.finish_consultation() при переходе консультации в FINISHED.
Запись (Egress) заканчивается асинхронно уже после этого момента — recording_url
приходит позже отдельным webhook-событием egress_ended, поэтому задача ждёт его
через self.retry вместо блокирующего опроса.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

_EGRESS_FAILURE_STATUSES = {'EGRESS_FAILED', 'EGRESS_ABORTED'}
_RETRY_COUNTDOWN_SECONDS = 30
_MAX_RETRIES = 20  # ~10 минут ожидания готовности записи


@shared_task(bind=True, name='appointments.generate_consultation_summary', max_retries=_MAX_RETRIES)
def generate_consultation_summary(self, consultation_id: int) -> None:
    from appointments.models import Appointment

    try:
        appointment = Appointment.objects.select_related('doctor__user', 'patient').get(pk=consultation_id)
    except Appointment.DoesNotExist:
        logger.warning('generate_consultation_summary: consultation_id=%s не найдена', consultation_id)
        return

    if not appointment.egress_id:
        logger.info(
            'generate_consultation_summary: consultation=%s без записи — резюме не строим',
            consultation_id,
        )
        return

    if appointment.egress_status in _EGRESS_FAILURE_STATUSES:
        logger.error(
            'generate_consultation_summary: consultation=%s запись завершилась с ошибкой (%s)',
            consultation_id, appointment.egress_status,
        )
        return

    if not appointment.recording_url:
        logger.info(
            'generate_consultation_summary: consultation=%s запись ещё не готова, повтор через %sс',
            consultation_id, _RETRY_COUNTDOWN_SECONDS,
        )
        raise self.retry(countdown=_RETRY_COUNTDOWN_SECONDS)

    from appointments.ai_summary import generate_and_deliver_summary

    try:
        generate_and_deliver_summary(appointment)
    except Exception:
        logger.exception(
            'generate_consultation_summary: ошибка AI-обработки consultation=%s', consultation_id,
        )
        raise
