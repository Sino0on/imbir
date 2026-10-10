import uuid
import logging
from datetime import datetime, timedelta

from django.conf import settings

logger = logging.getLogger(__name__)

# Длительность записи по умолчанию, если у услуги не указана (или услуга вообще
# не выбрана) — совпадает с шагом слотов в DoctorAvailableSlotsView.
DEFAULT_APPOINTMENT_DURATION_MINUTES = 30


def appointment_duration_minutes(service) -> int:
    if service and service.duration:
        return service.duration
    return DEFAULT_APPOINTMENT_DURATION_MINUTES


def appointment_time_range(date, time, service):
    """(start_datetime, end_datetime) записи с этой услугой (или дефолтной длительностью)."""
    start_dt = datetime.combine(date, time)
    end_dt = start_dt + timedelta(minutes=appointment_duration_minutes(service))
    return start_dt, end_dt


WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def _parse_hhmm(value):
    try:
        return datetime.strptime(value, '%H:%M').time()
    except (TypeError, ValueError):
        return None


# Конец рабочего дня, который означает «до полуночи»: пресет «24/7» в кабинете
# врача сохраняет 00:00–23:59, и последний слот (23:30–00:00) не помещался бы
# в день, кончающийся в 23:59. А '24:00' strptime вообще не разбирает.
_END_OF_DAY_VALUES = {'23:59', '24:00'}


def doctor_work_hours(doctor, date):
    """(start_datetime, end_datetime) рабочего дня врача на эту дату или None, если
    в этот день он не принимает (выходной, нет графика или его не разобрать).

    Конец '23:59'/'24:00' считается полуночью следующего дня. Ночные смены
    (конец раньше начала, например 20:00–08:00) и перерыв на конкретный день
    пока не поддерживаются: lunch_break у врача один на все дни, а смена через
    полночь — продуктовое решение (к какому дню относить слоты и выходные),
    а не правка формата."""
    day = (doctor.schedule or {}).get(WEEKDAYS[date.weekday()])
    if not isinstance(day, dict) or not day.get('enabled', True):
        return None
    start = _parse_hhmm(day.get('from') or day.get('start'))
    raw_end = day.get('to') or day.get('end')
    if not start:
        return None
    if isinstance(raw_end, str) and raw_end.strip() in _END_OF_DAY_VALUES:
        return (
            datetime.combine(date, start),
            datetime.combine(date + timedelta(days=1), datetime.min.time()),
        )
    end = _parse_hhmm(raw_end)
    if not end:
        return None
    return datetime.combine(date, start), datetime.combine(date, end)


def doctor_lunch_break(doctor, date):
    """(start_datetime, end_datetime) перерыва врача на эту дату или None."""
    lunch = doctor.lunch_break
    if not isinstance(lunch, dict):
        return None
    start = _parse_hhmm(lunch.get('from') or lunch.get('start'))
    end = _parse_hhmm(lunch.get('to') or lunch.get('end'))
    if not start or not end:
        return None
    return datetime.combine(date, start), datetime.combine(date, end)


def appointment_start_is_past(date, time):
    """True, если начало записи уже наступило по местному времени (TIME_ZONE) —
    записаться или перенести запись на такое время нельзя. Граница та же, что
    у слотов (DoctorAvailableSlotsView): слот на текущую минуту уже недоступен."""
    from django.utils import timezone

    local_now = timezone.localtime(timezone.now()).replace(tzinfo=None)
    return datetime.combine(date, time) <= local_now


def schedule_conflict(doctor, date, time, service):
    """Текст ошибки, если запись [time, time + длительность услуги) не помещается в
    рабочий день врача или задевает его перерыв; None, если всё в порядке.
    Те же правила, что у свободных слотов (DoctorAvailableSlotsView)."""
    work_hours = doctor_work_hours(doctor, date)
    if work_hours is None:
        return 'Врач не принимает в этот день — выберите другую дату.'

    start, end = appointment_time_range(date, time, service)
    minutes = appointment_duration_minutes(service)
    work_start, work_end = work_hours
    if start < work_start or end > work_end:
        # Конец дня «до полуночи» — это 00:00 следующих суток, пишем его как 24:00.
        work_end_label = '24:00' if work_end.date() > date else f'{work_end:%H:%M}'
        return (
            f'Приём длится {minutes} мин и не помещается в рабочее время врача '
            f'({work_start:%H:%M}–{work_end_label}) — выберите другое время.'
        )

    lunch = doctor_lunch_break(doctor, date)
    if lunch and start < lunch[1] and lunch[0] < end:
        return (
            f'Приём длится {minutes} мин и попадает на перерыв врача '
            f'({lunch[0]:%H:%M}–{lunch[1]:%H:%M}) — выберите другое время.'
        )
    return None


def find_overlapping_appointment(doctor, date, time, service, exclude_id=None):
    """Первая активная запись этого врача на эту дату, чей интервал [start, end)
    пересекается с новым — с учётом длительности услуги каждой из записей.
    None, если конфликтов нет."""
    from .models import Appointment

    new_start, new_end = appointment_time_range(date, time, service)

    qs = Appointment.objects.filter(
        doctor=doctor, date=date,
        status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED, Appointment.Status.COMPLETED],
    ).select_related('service')
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)

    for existing in qs:
        existing_start, existing_end = appointment_time_range(existing.date, existing.time, existing.service)
        if new_start < existing_end and existing_start < new_end:
            return existing
    return None


def generate_meet_link(appointment_date, appointment_time, title='Онлайн-приём', duration_minutes=None):
    """
    Creates a Google Calendar event with a Meet link on behalf of a real Google user.
    duration_minutes — длительность события, appointment_duration_minutes(услуги);
    если не передана — DEFAULT_APPOINTMENT_DURATION_MINUTES.
    Requires OAuth2 env vars: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REFRESH_TOKEN, GOOGLE_CALENDAR_CALENDAR_ID.

    Returns the Meet link URL or None if the Google API call fails.
    """
    refresh_token = getattr(settings, 'GOOGLE_OAUTH_REFRESH_TOKEN', None)
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None)

    if not all([refresh_token, client_id, client_secret]):
        logger.warning('Google OAuth credentials not configured — skipping Meet link.')
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
        )
        creds.refresh(Request())

        service = build('calendar', 'v3', credentials=creds)

        start_dt = datetime.combine(appointment_date, appointment_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes or DEFAULT_APPOINTMENT_DURATION_MINUTES)

        event_body = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': settings.TIME_ZONE},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': settings.TIME_ZONE},
            'conferenceData': {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                }
            },
        }

        calendar_id = getattr(settings, 'GOOGLE_CALENDAR_CALENDAR_ID', 'primary')
        created = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            conferenceDataVersion=1,
        ).execute()

        for ep in created.get('conferenceData', {}).get('entryPoints', []):
            if ep.get('entryPointType') == 'video':
                return ep['uri']

        logger.warning('Google Calendar API did not return a Meet link for the event.')
        return None

    except Exception as exc:
        logger.error('Failed to generate Google Meet link: %s', exc)
        return None

