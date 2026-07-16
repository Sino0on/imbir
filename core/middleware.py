import json
import logging
import urllib.request
from django.conf import settings

logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')
    return ip


def get_city_from_ip(ip):
    if not ip or ip in ('127.0.0.1', 'localhost', '::1'):
        return None

    url = f"http://ip-api.com/json/{ip}?lang=ru"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'success':
                return data.get('city')
    except Exception as e:
        logger.warning(f"Error fetching city for IP {ip}: {e}")
    return None


class CityFromIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Check if city is explicitly passed in query params (to allow user to override)
        city = request.GET.get('city') or request.GET.get('current_city')

        if city:
            city = city.strip()
            # Save to session if session middleware is active
            if hasattr(request, 'session'):
                request.session['detected_city'] = city
        else:
            # 2. Check if we already have it in session
            if hasattr(request, 'session'):
                city = request.session.get('detected_city')

            # 3. If not in session, detect via IP
            if not city:
                ip = get_client_ip(request)
                city = get_city_from_ip(ip)

                # Save to session if found
                if city and hasattr(request, 'session'):
                    request.session['detected_city'] = city

        # 4. Fallback to default city if detection failed or is empty
        if not city:
            city = getattr(settings, 'DEFAULT_CITY', 'Бишкек')

        request.city = city

        response = self.get_response(request)
        return response
