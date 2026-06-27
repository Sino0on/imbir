"""
Запусти один раз: python get_google_token.py
Откроется браузер — войди под своим Gmail аккаунтом и разреши доступ.
Скрипт выведет GOOGLE_OAUTH_REFRESH_TOKEN — скопируй его в .env
"""
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = input('Вставь Google OAuth Client ID: ').strip()
CLIENT_SECRET = input('Вставь Google OAuth Client Secret: ').strip()

flow = InstalledAppFlow.from_client_config(
    {
        'installed': {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uris': ['http://localhost'],
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    },
    scopes=['https://www.googleapis.com/auth/calendar.events'],
)

creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

print('\n=== Готово! Добавь в .env ===')
print(f'GOOGLE_OAUTH_CLIENT_ID={CLIENT_ID}')
print(f'GOOGLE_OAUTH_CLIENT_SECRET={CLIENT_SECRET}')
print(f'GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}')
