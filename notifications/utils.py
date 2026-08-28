def notify(user, type, title, body='', payload=None):
    """Создаёт уведомление пользователю. user может быть None (гостевая запись
    без аккаунта, например) — в этом случае просто ничего не делает."""
    if not user:
        return None

    from .models import Notification
    return Notification.objects.create(
        user=user, type=type, title=title, body=body, payload=payload or {},
    )


# Фиксированная форма payload на тип уведомления — чтобы фронт мог по клику
# вести на конкретную запись/отзыв/чат, а не в общий список. Все builder'ы
# ниже — единственное место, где формируется payload для своего типа.

def appointment_payload(appointment):
    """appointment_created / appointment_confirmed / appointment_cancelled /
    appointment_completed / appointment_reminder."""
    return {
        'appointment_id': appointment.id,
        'doctor_id': appointment.doctor.user_id if appointment.doctor else None,
        'clinic_id': appointment.clinic.user_id if appointment.clinic else None,
        'date': appointment.date.isoformat(),
        'time': appointment.time.strftime('%H:%M'),
    }


def review_payload(review):
    """new_review."""
    target_id = review.doctor.user_id if review.doctor else review.clinic.user_id
    return {
        'review_id': review.id,
        'target_type': review.target_type,
        'target_id': target_id,
    }


def message_payload(room_id):
    """new_message."""
    return {'room_id': room_id}
