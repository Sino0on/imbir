import ipaddress
import json
import logging
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.utils.functional import SimpleLazyObject

logger = logging.getLogger(__name__)

# Город по IP нужен только каталогам врачей и клиник без ?city=, а ip-api.com
# бесплатно отвечает на 45 запросов в минуту. Раньше его звали на каждом
# запросе к API с таймаутом 3 с: сверх лимита запросы сайта (и ИИ-чата) ждали
# эти 3 с, держа соединение с БД. Теперь — лениво, с кешем по IP и коротким
# таймаутом.
GEO_TIMEOUT_SECONDS = 1
GEO_CACHE_SECONDS = 24 * 60 * 60
# Неудачу тоже запоминаем, но ненадолго: иначе при недоступном ip-api каждый
# запрос заново ждал бы таймаут.
GEO_MISS_CACHE_SECONDS = 10 * 60


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')
    return ip


def _is_public_ip(ip):
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def get_city_from_ip(ip):
    # Локальные и внутренние адреса (Docker, локальная сеть) ip-api не
    # определит — не тратим на них ни лимит, ни таймаут.
    if not ip or not _is_public_ip(ip):
        return None

    url = f"http://ip-api.com/json/{ip}?lang=ru"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=GEO_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'success':
                return data.get('city')
    except Exception as e:
        logger.warning(f"Error fetching city for IP {ip}: {e}")
    return None


def detect_city(request):
    """Город запроса: явный ?city=, иначе по IP (с кешем), иначе город по умолчанию."""
    city = (request.GET.get('city') or request.GET.get('current_city') or '').strip()
    if city:
        return city

    ip = get_client_ip(request)
    key = f'geo-city:{ip}'
    cached = cache.get(key)
    if cached is None:
        cached = get_city_from_ip(ip) or ''
        cache.set(key, cached, GEO_CACHE_SECONDS if cached else GEO_MISS_CACHE_SECONDS)
    return cached or getattr(settings, 'DEFAULT_CITY', 'Бишкек')


class CityFromIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Лениво: город вычисляется, только если вьюха обратилась к
        # request.city. Сессию не трогаем — фронт ходит на API с другого
        # домена без cookie, и каждая запись в сессию создавала в БД новую
        # строку django_session, которую никто больше не читал.
        request.city = SimpleLazyObject(lambda: detect_city(request))
        return self.get_response(request)
