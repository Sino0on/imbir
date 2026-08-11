"""Бизнес-логика LiveKit: комнаты, выдача токенов, обработка событий вебхука, запись."""
import logging
import os

from django.conf import settings
from django.utils import timezone
from livekit import api

from appointments.models import Appointment
from . import client
from . import permissions
from . import token as token_service
from .token import role_from_identity

logger = logging.getLogger(__name__)

_EGRESS_TERMINAL_STATUSES = {'EGRESS_COMPLETE', 'EGRESS_FAILED', 'EGRESS_ABORTED'}


def room_name_for(appointment: Appointment) -> str:
    return f'consultation-{appointment.id}'


def ensure_room(appointment: Appointment) -> str:
    """Обеспечить наличие комнаты LiveKit для консультации.

    LiveKit CreateRoom идемпотентен: если комната с таким именем уже существует,
    возвращается существующая — повторный create_room ничего не ломает.
    """
    room_name = appointment.room_name or room_name_for(appointment)

    room = client.run_sync(
        lambda c: c.room.create_room(api.CreateRoomRequest(name=room_name))
    )
    logger.info(
        'LiveKit: комната готова consultation=%s room=%s sid=%s',
        appointment.id, room.name, room.sid,
    )

    update_fields = []
    if appointment.room_name != room_name:
        appointment.room_name = room_name
        update_fields.append('room_name')
    if not appointment.livekit_room_created:
        appointment.livekit_room_created = True
        update_fields.append('livekit_room_created')
    if update_fields:
        appointment.save(update_fields=update_fields + ['updated_at'])

    return room_name


def generate_token_for_participant(appointment: Appointment, user) -> dict:
    """Полный сценарий GET /api/livekit/token/: проверки → комната → токен."""
    role = permissions.ensure_can_join(appointment, user)
    room_name = ensure_room(appointment)

    identity = token_service.build_identity(role, user.id)
    display_name = getattr(user, 'full_name', None) or user.email

    jwt = token_service.generate_access_token(
        identity=identity,
        name=display_name,
        room=room_name,
    )

    logger.info(
        'LiveKit: выдан токен consultation=%s role=%s user=%s room=%s',
        appointment.id, role, user.id, room_name,
    )

    return {
        'url': settings.LIVEKIT_URL,
        'room': room_name,
        'token': jwt,
    }


def _get_appointment_by_room(room_name: str) -> Appointment | None:
    qs = Appointment.objects.filter(room_name=room_name).order_by('-created_at')
    appointment = qs.first()
    if appointment is None:
        logger.warning('LiveKit webhook: консультация для комнаты "%s" не найдена', room_name)
    return appointment


# --- Webhook event handlers -------------------------------------------------

def handle_participant_joined(event) -> None:
    appointment = _get_appointment_by_room(event.room.name)
    if appointment is None:
        return

    role = role_from_identity(event.participant.identity)
    logger.info(
        'LiveKit: участник подключился consultation=%s role=%s identity=%s',
        appointment.id, role, event.participant.identity,
    )

    update_fields = []
    if role == token_service.DOCTOR_ROLE and not appointment.doctor_joined:
        appointment.doctor_joined = True
        update_fields.append('doctor_joined')
    elif role == token_service.PATIENT_ROLE and not appointment.patient_joined:
        appointment.patient_joined = True
        update_fields.append('patient_joined')

    if appointment.doctor_joined and appointment.patient_joined:
        if appointment.consultation_status != Appointment.ConsultationStatus.ACTIVE:
            appointment.consultation_status = Appointment.ConsultationStatus.ACTIVE
            update_fields.append('consultation_status')
        if appointment.started_at is None:
            appointment.started_at = timezone.now()
            update_fields.append('started_at')
    elif appointment.consultation_status == Appointment.ConsultationStatus.CREATED:
        appointment.consultation_status = Appointment.ConsultationStatus.WAITING
        update_fields.append('consultation_status')

    if update_fields:
        appointment.save(update_fields=update_fields + ['updated_at'])


def handle_participant_left(event) -> None:
    appointment = _get_appointment_by_room(event.room.name)
    if appointment is None:
        return

    role = role_from_identity(event.participant.identity)
    logger.info(
        'LiveKit: участник отключился consultation=%s role=%s identity=%s',
        appointment.id, role, event.participant.identity,
    )

    update_fields = []
    if role == token_service.DOCTOR_ROLE and appointment.doctor_joined:
        appointment.doctor_joined = False
        update_fields.append('doctor_joined')
    elif role == token_service.PATIENT_ROLE and appointment.patient_joined:
        appointment.patient_joined = False
        update_fields.append('patient_joined')

    if update_fields:
        appointment.save(update_fields=update_fields + ['updated_at'])

    both_left = not appointment.doctor_joined and not appointment.patient_joined
    if both_left and appointment.consultation_status not in (
        Appointment.ConsultationStatus.FINISHED,
        Appointment.ConsultationStatus.CANCELLED,
    ):
        finish_consultation(appointment)


def handle_track_published(event) -> None:
    """Публикация микрофона участником — запускаем запись именно его дорожки.

    Записываем врача и пациента отдельными аудиодорожками (не общую комнату),
    чтобы потом однозначно знать, кто что сказал, без угадывания по смыслу.
    """
    if not settings.LIVEKIT_RECORDING_ENABLED:
        return

    track = event.track
    if track.source != api.TrackSource.MICROPHONE:
        return

    appointment = _get_appointment_by_room(event.room.name)
    if appointment is None:
        return

    role = role_from_identity(event.participant.identity)
    if role not in (token_service.DOCTOR_ROLE, token_service.PATIENT_ROLE):
        return

    if getattr(appointment, f'{role}_egress_id'):
        logger.info(
            'LiveKit: запись для роли %s уже запущена consultation=%s',
            role, appointment.id,
        )
        return

    start_track_recording(appointment, role, track.sid)


def handle_room_started(event) -> None:
    appointment = _get_appointment_by_room(event.room.name)
    if appointment is None:
        return
    logger.info(
        'LiveKit: получено событие room_started consultation=%s sid=%s',
        appointment.id, event.room.sid,
    )


def handle_room_finished(event) -> None:
    appointment = _get_appointment_by_room(event.room.name)
    if appointment is None:
        return
    logger.info('LiveKit: получено событие room_finished consultation=%s', appointment.id)
    finish_consultation(appointment)


def finish_consultation(appointment: Appointment) -> None:
    if appointment.consultation_status == Appointment.ConsultationStatus.FINISHED:
        return

    appointment.consultation_status = Appointment.ConsultationStatus.FINISHED
    appointment.ended_at = timezone.now()
    appointment.save(update_fields=['consultation_status', 'ended_at', 'updated_at'])
    logger.info('LiveKit: консультация завершена consultation=%s', appointment.id)

    for role in (token_service.DOCTOR_ROLE, token_service.PATIENT_ROLE):
        egress_id = getattr(appointment, f'{role}_egress_id')
        egress_status = getattr(appointment, f'{role}_egress_status')
        if egress_id and egress_status not in _EGRESS_TERMINAL_STATUSES:
            stop_track_recording(appointment, role)

    dispatch_summary_task(appointment)


# --- Запись (Egress) ---------------------------------------------------------
#
# Каждый участник пишется отдельной аудиодорожкой (TrackEgress), а не общей
# комнатой (RoomCompositeEgress) — так расшифровка каждого файла достоверно
# принадлежит конкретной роли, без угадывания "кто это сказал" по смыслу фразы.

def _build_track_output(appointment: Appointment, role: str) -> 'api.DirectFileOutput':
    filepath = settings.LIVEKIT_RECORDING_LOCAL_PATH.format(
        room_name=f'{appointment.room_name}-{role}', time='{time}'
    )
    output = api.DirectFileOutput(filepath=filepath)
    if settings.LIVEKIT_S3_BUCKET:
        output.s3.CopyFrom(api.S3Upload(
            access_key=settings.LIVEKIT_S3_ACCESS_KEY,
            secret=settings.LIVEKIT_S3_SECRET_KEY,
            bucket=settings.LIVEKIT_S3_BUCKET,
            region=settings.LIVEKIT_S3_REGION,
            endpoint=settings.LIVEKIT_S3_ENDPOINT,
        ))
    return output


def start_track_recording(appointment: Appointment, role: str, track_sid: str) -> None:
    if getattr(appointment, f'{role}_egress_id'):
        logger.info(
            'LiveKit: запись роли %s уже запущена consultation=%s',
            role, appointment.id,
        )
        return

    request = api.TrackEgressRequest(
        room_name=appointment.room_name,
        track_id=track_sid,
        file=_build_track_output(appointment, role),
    )

    try:
        info = client.run_sync(lambda c: c.egress.start_track_egress(request))
    except Exception:
        logger.exception(
            'LiveKit: не удалось запустить запись роли %s consultation=%s',
            role, appointment.id,
        )
        return

    setattr(appointment, f'{role}_egress_id', info.egress_id)
    setattr(appointment, f'{role}_egress_status', api.EgressStatus.Name(info.status))
    appointment.save(update_fields=[f'{role}_egress_id', f'{role}_egress_status', 'updated_at'])
    logger.info(
        'LiveKit: запись роли %s запущена consultation=%s egress_id=%s',
        role, appointment.id, info.egress_id,
    )


def stop_track_recording(appointment: Appointment, role: str) -> None:
    egress_id = getattr(appointment, f'{role}_egress_id')
    if not egress_id:
        return
    try:
        client.run_sync(lambda c: c.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id)))
        logger.info(
            'LiveKit: запись роли %s остановлена consultation=%s egress_id=%s',
            role, appointment.id, egress_id,
        )
    except Exception:
        logger.exception(
            'LiveKit: не удалось остановить запись роли %s consultation=%s',
            role, appointment.id,
        )


def handle_egress_updated(event) -> None:
    """egress_started / egress_updated / egress_ended — все несут egress_info."""
    from django.db.models import Q

    info = event.egress_info
    if not info or not info.egress_id:
        return

    appointment = (
        Appointment.objects
        .filter(Q(doctor_egress_id=info.egress_id) | Q(patient_egress_id=info.egress_id))
        .order_by('-created_at')
        .first()
    )
    if appointment is None:
        logger.warning('LiveKit webhook: консультация для egress_id=%s не найдена', info.egress_id)
        return

    role = (
        token_service.DOCTOR_ROLE if appointment.doctor_egress_id == info.egress_id
        else token_service.PATIENT_ROLE
    )

    status_name = api.EgressStatus.Name(info.status)
    update_fields = []
    if getattr(appointment, f'{role}_egress_status') != status_name:
        setattr(appointment, f'{role}_egress_status', status_name)
        update_fields.append(f'{role}_egress_status')

    if status_name == 'EGRESS_COMPLETE' and info.file_results:
        recording_url = info.file_results[0].location
        if recording_url and getattr(appointment, f'{role}_recording_url') != recording_url:
            setattr(appointment, f'{role}_recording_url', recording_url)
            update_fields.append(f'{role}_recording_url')
        logger.info(
            'LiveKit: запись роли %s завершена consultation=%s egress_id=%s url=%s',
            role, appointment.id, info.egress_id, recording_url,
        )
    elif status_name in ('EGRESS_FAILED', 'EGRESS_ABORTED'):
        logger.error(
            'LiveKit: ошибка записи роли %s consultation=%s egress_id=%s error=%s',
            role, appointment.id, info.egress_id, info.error,
        )

    if update_fields:
        appointment.save(update_fields=update_fields + ['updated_at'])


def fetch_recording_bytes(appointment: Appointment, role: str) -> tuple[bytes, str]:
    """Скачивает файл записи роли (doctor/patient). Возвращает (содержимое, имя_файла).

    location ({role}_recording_url) — то, что LiveKit Egress вернул в file_results:
    URL до объекта в S3-совместимом хранилище (без подписи — это не presigned-ссылка,
    просто адрес бакета+ключа) или локальный путь на диске egress-воркера
    (см. LIVEKIT_RECORDING_LOCAL_PATH).

    Если бакет у нас настроен (LIVEKIT_S3_BUCKET), он приватный, и скачивать нужно
    только через авторизованный boto3-клиент — обычный requests.get() без подписи
    получит 400/403 от хранилища, даже если location выглядит как обычный URL.
    """
    location = getattr(appointment, f'{role}_recording_url')
    if not location:
        raise ValueError(f'consultation={appointment.id}: {role}_recording_url пуст')

    if settings.LIVEKIT_S3_BUCKET:
        import boto3

        if location.startswith('http://') or location.startswith('https://'):
            from urllib.parse import urlparse, unquote
            key = unquote(urlparse(location).path)
        else:
            key = location

        # LIVEKIT_RECORDING_LOCAL_PATH обычно начинается с "/" (например "/out/{...}"),
        # и этот "/" — часть реального ключа объекта в бакете, его нельзя обрезать.
        # Бакет из пути убираем только если он там явно присутствует (path-style адрес).
        bucket = settings.LIVEKIT_S3_BUCKET
        if key.startswith(f'/{bucket}/'):
            key = key[len(bucket) + 1:]
        elif key.startswith(f'{bucket}/'):
            key = key[len(bucket):]

        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.LIVEKIT_S3_ACCESS_KEY,
            aws_secret_access_key=settings.LIVEKIT_S3_SECRET_KEY,
            region_name=settings.LIVEKIT_S3_REGION or None,
            endpoint_url=settings.LIVEKIT_S3_ENDPOINT or None,
        )
        obj = s3.get_object(Bucket=settings.LIVEKIT_S3_BUCKET, Key=key)
        return obj['Body'].read(), os.path.basename(key)

    if location.startswith('http://') or location.startswith('https://'):
        import requests
        resp = requests.get(location, timeout=120)
        resp.raise_for_status()
        return resp.content, os.path.basename(location.split('?', 1)[0])

    with open(location, 'rb') as f:
        return f.read(), os.path.basename(location)


# --- Подготовка к AI-обработке ----------------------------------------------

def dispatch_summary_task(appointment: Appointment) -> None:
    """Точка входа для дальнейшей AI-обработки: ставим Celery-задачу в очередь.

    Задача ждёт готовности записи и строит резюме через appointments.ai_summary
    (расшифровка Whisper → резюме GPT-4o-mini → доставка в чат).
    """
    from appointments.tasks import generate_consultation_summary

    generate_consultation_summary.delay(appointment.id)
    logger.info('LiveKit: поставлена задача generate_consultation_summary consultation=%s', appointment.id)
