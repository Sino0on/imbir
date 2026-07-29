"""AI-обработка завершённой консультации: расшифровка записи → резюме → отправка в чат.

Вызывается из tasks.generate_consultation_summary после того, как запись (Egress)
готова (appointment.recording_url заполнен).
"""
import io
import logging

from django.conf import settings
from django.utils import timezone
from openai import OpenAI

from livekit_integration.services import fetch_recording_bytes

logger = logging.getLogger(__name__)

# Лимит Whisper API на размер файла.
MAX_TRANSCRIBE_BYTES = 25 * 1024 * 1024

SUMMARY_SYSTEM_PROMPT = (
    'Ты медицинский ассистент. Тебе дана расшифровка видео-консультации врача и пациента. '
    'Составь краткое структурированное резюме на русском языке по разделам: '
    '"Жалобы пациента", "Что обсудили", "Рекомендации врача", "Дальнейшие шаги". '
    'Опирайся только на то, что реально прозвучало в разговоре, ничего не придумывай. '
    'Если содержимого недостаточно для содержательного резюме — так и напиши одной строкой.'
)


def transcribe_recording(appointment) -> str:
    content, filename = fetch_recording_bytes(appointment)
    if len(content) > MAX_TRANSCRIBE_BYTES:
        raise ValueError(
            f'consultation={appointment.id}: запись слишком большая для Whisper '
            f'({len(content)} байт, лимит {MAX_TRANSCRIBE_BYTES})'
        )

    file_obj = io.BytesIO(content)
    file_obj.name = filename or f'consultation-{appointment.id}.mp4'

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    transcript = client.audio.transcriptions.create(
        model='whisper-1',
        file=file_obj,
        language='ru',
    )
    return transcript.text


def summarize_transcript(transcript: str) -> str:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    completion = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {'role': 'system', 'content': SUMMARY_SYSTEM_PROMPT},
            {'role': 'user', 'content': transcript},
        ],
    )
    return completion.choices[0].message.content.strip()


def send_summary_to_chat(appointment, summary_text: str) -> None:
    from chat.services import get_or_create_room, send_system_message

    doctor_user = appointment.doctor.user if appointment.doctor else None
    patient_user = appointment.patient
    if not doctor_user or not patient_user:
        logger.warning(
            'AI-резюме consultation=%s: нет врача или пациента, отправлять некуда',
            appointment.id,
        )
        return

    room = get_or_create_room(patient_user, doctor_user)
    content = f'Резюме консультации (сформировано автоматически):\n\n{summary_text}'
    send_system_message(room, content)
    logger.info('AI-резюме consultation=%s отправлено в чат room=%s', appointment.id, room.id)


def generate_and_deliver_summary(appointment) -> None:
    logger.info('AI-резюме consultation=%s: начинаем расшифровку записи', appointment.id)
    transcript = transcribe_recording(appointment)
    logger.info(
        'AI-резюме consultation=%s: расшифровка готова (%d симв.)',
        appointment.id, len(transcript),
    )

    summary = summarize_transcript(transcript)
    logger.info('AI-резюме consultation=%s: резюме сформировано', appointment.id)

    appointment.ai_summary = summary
    appointment.ai_summary_generated_at = timezone.now()
    appointment.save(update_fields=['ai_summary', 'ai_summary_generated_at', 'updated_at'])

    send_summary_to_chat(appointment, summary)
