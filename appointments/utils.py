import uuid
from datetime import datetime, timedelta

from django.conf import settings


def generate_meet_link(appointment_date, appointment_time, title='Онлайн-приём'):
    """
    Creates a Google Calendar event with a Meet link on behalf of a real Google user.
    Requires OAuth2 env vars: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REFRESH_TOKEN, GOOGLE_CALENDAR_CALENDAR_ID.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=settings.GOOGLE_OAUTH_REFRESH_TOKEN,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
    )
    creds.refresh(Request())

    service = build('calendar', 'v3', credentials=creds)

    start_dt = datetime.combine(appointment_date, appointment_time)
    end_dt = start_dt + timedelta(hours=1)

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

    raise RuntimeError('Calendar API не вернул Meet-ссылку.')
