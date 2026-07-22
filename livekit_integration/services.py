"""Бизнес-логика LiveKit: комнаты, выдача токенов, обработка событий вебхука, запись."""
import logging

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

    if (
        appointment.doctor_joined and appointment.patient_joined
        and settings.LIVEKIT_RECORDING_ENABLED and not appointment.egress_id
    ):
        start_recording(appointment)


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

    if appointment.egress_id and appointment.egress_status not in _EGRESS_TERMINAL_STATUSES:
        stop_recording(appointment)

    dispatch_summary_task(appointment)


# --- Запись (Egress) ---------------------------------------------------------

def _build_file_output(appointment: Appointment) -> 'api.EncodedFileOutput':
    filepath = settings.LIVEKIT_RECORDING_LOCAL_PATH.format(
        room_name=appointment.room_name, time='{time}'
    )
    output = api.EncodedFileOutput(
        file_type=api.EncodedFileType.MP4,
        filepath=filepath,
    )
    if settings.LIVEKIT_S3_BUCKET:
        output.s3.CopyFrom(api.S3Upload(
            access_key=settings.LIVEKIT_S3_ACCESS_KEY,
            secret=settings.LIVEKIT_S3_SECRET_KEY,
            bucket=settings.LIVEKIT_S3_BUCKET,
            region=settings.LIVEKIT_S3_REGION,
            endpoint=settings.LIVEKIT_S3_ENDPOINT,
        ))
    return output


def start_recording(appointment: Appointment) -> None:
    if appointment.egress_id:
        logger.info(
            'LiveKit: запись уже запущена consultation=%s egress_id=%s',
            appointment.id, appointment.egress_id,
        )
        return

    request = api.RoomCompositeEgressRequest(
        room_name=appointment.room_name,
        layout='speaker',
        file_outputs=[_build_file_output(appointment)],
    )

    try:
        info = client.run_sync(lambda c: c.egress.start_room_composite_egress(request))
    except Exception:
        logger.exception('LiveKit: не удалось запустить запись consultation=%s', appointment.id)
        return

    appointment.egress_id = info.egress_id
    appointment.egress_status = api.EgressStatus.Name(info.status)
    appointment.save(update_fields=['egress_id', 'egress_status', 'updated_at'])
    logger.info(
        'LiveKit: запись запущена consultation=%s egress_id=%s',
        appointment.id, appointment.egress_id,
    )


def stop_recording(appointment: Appointment) -> None:
    if not appointment.egress_id:
        return
    try:
        client.run_sync(lambda c: c.egress.stop_egress(api.StopEgressRequest(egress_id=appointment.egress_id)))
        logger.info('LiveKit: запись остановлена consultation=%s egress_id=%s', appointment.id, appointment.egress_id)
    except Exception:
        logger.exception('LiveKit: не удалось остановить запись consultation=%s', appointment.id)


def handle_egress_updated(event) -> None:
    """egress_started / egress_updated / egress_ended — все несут egress_info."""
    info = event.egress_info
    if not info or not info.egress_id:
        return

    appointment = Appointment.objects.filter(egress_id=info.egress_id).order_by('-created_at').first()
    if appointment is None:
        logger.warning('LiveKit webhook: консультация для egress_id=%s не найдена', info.egress_id)
        return

    status_name = api.EgressStatus.Name(info.status)
    update_fields = []
    if appointment.egress_status != status_name:
        appointment.egress_status = status_name
        update_fields.append('egress_status')

    if status_name == 'EGRESS_COMPLETE' and info.file_results:
        recording_url = info.file_results[0].location
        if recording_url and appointment.recording_url != recording_url:
            appointment.recording_url = recording_url
            update_fields.append('recording_url')
        logger.info(
            'LiveKit: запись завершена consultation=%s egress_id=%s url=%s',
            appointment.id, info.egress_id, recording_url,
        )
    elif status_name in ('EGRESS_FAILED', 'EGRESS_ABORTED'):
        logger.error(
            'LiveKit: ошибка записи consultation=%s egress_id=%s error=%s',
            appointment.id, info.egress_id, info.error,
        )

    if update_fields:
        appointment.save(update_fields=update_fields + ['updated_at'])


# --- Подготовка к AI-обработке ----------------------------------------------

def dispatch_summary_task(appointment: Appointment) -> None:
    """Точка входа для дальнейшей AI-обработки: ставим Celery-задачу в очередь.

    Сама задача пока — заглушка (см. appointments/tasks.py).
    """
    from appointments.tasks import generate_consultation_summary

    generate_consultation_summary.delay(appointment.id)
    logger.info('LiveKit: поставлена задача generate_consultation_summary consultation=%s', appointment.id)
