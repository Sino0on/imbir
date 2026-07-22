"""
Celery-задачи по консультациям.

По ТЗ (п.13, "Подготовка к AI"): после завершения консультации backend должен
поставить в очередь задачу generate_consultation_summary(consultation_id).
Реализация самой AI-обработки на этом этапе не требуется — нужна только точка
входа, которую дальше можно наполнить логикой (расшифровка записи, саммари и т.д.).

Точка вызова — livekit_integration.services.dispatch_summary_task(),
которая вызывается из finish_consultation() при переходе консультации в FINISHED.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='appointments.generate_consultation_summary')
def generate_consultation_summary(consultation_id: int) -> None:
    """Заглушка: точка входа для будущей AI-обработки завершённой консультации.

    Ожидаемая будущая логика: дождаться готовности записи (recording_url),
    прогнать через ASR/LLM и сохранить резюме консультации.
    """
    logger.info(
        'generate_consultation_summary: задача поставлена для consultation_id=%s '
        '(AI-обработка ещё не реализована)',
        consultation_id,
    )
