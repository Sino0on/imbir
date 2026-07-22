"""Проверки доступа участника к консультации (кто и когда может получить токен)."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from appointments.models import Appointment
from .token import DOCTOR_ROLE, PATIENT_ROLE

logger = logging.getLogger(__name__)


def get_role(appointment: Appointment, user) -> Optional[str]:
    """'doctor' / 'patient', если user — участник консультации, иначе None."""
    if not user or not user.is_authenticated:
        return None
    if appointment.doctor_id and appointment.doctor.user_id == user.id:
        return DOCTOR_ROLE
    if appointment.patient_id and appointment.patient_id == user.id:
        return PATIENT_ROLE
    return None


def get_scheduled_datetime(appointment: Appointment) -> datetime:
    naive = datetime.combine(appointment.date, appointment.time)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def ensure_can_join(appointment: Appointment, user) -> str:
    """Полная проверка перед выдачей токена. Возвращает роль пользователя.

    403 PermissionDenied — не участник консультации.
    400 ValidationError  — консультация существует, но подключение сейчас недоступно
                            (не оплачена / отменена / не время).
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied('Требуется авторизация.')

    role = get_role(appointment, user)
    if role is None:
        raise PermissionDenied('Вы не являетесь участником этой консультации.')

    if not appointment.is_online:
        raise ValidationError('Эта запись не является онлайн-консультацией.')

    if appointment.status == Appointment.Status.CANCELLED:
        raise ValidationError('Консультация отменена.')

    if not appointment.is_paid:
        raise ValidationError('Консультация ещё не оплачена.')

    if appointment.consultation_status == Appointment.ConsultationStatus.CANCELLED:
        raise ValidationError('Консультация отменена.')
    if appointment.consultation_status == Appointment.ConsultationStatus.FINISHED:
        raise ValidationError('Консультация уже завершена.')

    scheduled_at = get_scheduled_datetime(appointment)
    window = timedelta(minutes=settings.LIVEKIT_JOIN_WINDOW_MINUTES)
    now = timezone.now()

    too_early = now < scheduled_at - window
    too_late = now > scheduled_at + window

    # Если консультация уже идёт (ACTIVE), не отсекаем по опозданию — участник
    # мог переподключиться (обрыв связи и т.п.).
    if too_early:
        raise ValidationError('Консультация ещё недоступна: слишком рано для подключения.')
    if too_late and appointment.consultation_status != Appointment.ConsultationStatus.ACTIVE:
        raise ValidationError('Время подключения к консультации истекло.')

    return role
