import os
from urllib.parse import urlparse
from django.conf import settings

def get_relative_path_from_url(url):
    """
    Strips settings.MEDIA_URL prefix from absolute/relative media URLs to 
    get the relative path to be stored directly in a FileField/ImageField.
    """
    if not url:
        return None
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        media_url = settings.MEDIA_URL  # e.g., '/media/'
        if path.startswith(media_url):
            return path[len(media_url):].lstrip('/')
        if path.startswith('media/'):
            return path[len('media/'):].lstrip('/')
        return path.lstrip('/')
    except Exception:
        return url

def save_hybrid_documents(profile, field_name, model_class, request):
    """
    Saves documents/photos for a profile (DoctorProfile or ClinicProfile).
    Supports:
      1. request.FILES (file uploads)
      2. request.data (string URLs or list of string URLs)
    """
    # 1. Handle file uploads from request.FILES
    for uploaded_file in request.FILES.getlist(field_name):
        if field_name == 'photos':
            model_class.objects.create(clinic=profile, image=uploaded_file)
        elif field_name == 'documents':
            if hasattr(model_class, 'doctor'):
                model_class.objects.create(doctor=profile, file=uploaded_file)
            else:
                model_class.objects.create(clinic=profile, file=uploaded_file)

    # 2. Handle URLs from request.data
    urls_data = []
    if hasattr(request.data, 'getlist'):
        urls_data = request.data.getlist(field_name)
    else:
        urls_data = request.data.get(field_name)

    if urls_data:
        # If it is a string (e.g. JSON string of a list, or comma-separated list), parse/clean it
        if isinstance(urls_data, str):
            urls_data = urls_data.strip()
            if urls_data.startswith('[') and urls_data.endswith(']'):
                import json
                try:
                    urls_data = json.loads(urls_data)
                except ValueError:
                    urls_data = [u.strip() for u in urls_data.split(',') if u.strip()]
            else:
                urls_data = [u.strip() for u in urls_data.split(',') if u.strip()]
        elif not isinstance(urls_data, list):
            urls_data = [urls_data]

        for url in urls_data:
            if not isinstance(url, str) or not url.strip():
                continue
            rel_path = get_relative_path_from_url(url)
            if rel_path:
                if field_name == 'photos':
                    if not model_class.objects.filter(clinic=profile, image=rel_path).exists():
                        model_class.objects.create(clinic=profile, image=rel_path)
                elif field_name == 'documents':
                    if hasattr(model_class, 'doctor'):
                        if not model_class.objects.filter(doctor=profile, file=rel_path).exists():
                            model_class.objects.create(doctor=profile, file=rel_path)
                    else:
                        if not model_class.objects.filter(clinic=profile, file=rel_path).exists():
                            model_class.objects.create(clinic=profile, file=rel_path)


import urllib.request
import urllib.parse
import urllib.error
import json
import logging

logger = logging.getLogger(__name__)

def send_sms_nikita(phone, text):
    url = getattr(settings, 'NIKITA_SMS_URL', 'https://smspro.nikita.kg/api/send')
    login = getattr(settings, 'NIKITA_SMS_LOGIN', '')
    password = getattr(settings, 'NIKITA_SMS_PASSWORD', '')
    sender = getattr(settings, 'NIKITA_SMS_SENDER', 'Imbir')

    if not login or not password:
        logger.warning(f"Nikita SMS credentials not set. SMS to {phone} would be: {text}")
        print(f"\n--- SMS to {phone} (Nikita SMS simulation) ---\n{text}\n------------------------------------------\n")
        return True

    phone_cleaned = ''.join(c for c in phone if c.isdigit())
    payload = {
        "login": login,
        "password": password,
        "messages": [
            {
                "id": "1",
                "phone": phone_cleaned,
                "text": text,
                "sender": sender
            }
        ]
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read().decode('utf-8')
            logger.info(f"Nikita SMS sent to {phone}. Response: {res_data}")
            return True
    except Exception as e:
        logger.error(f"Failed to send SMS to {phone} via Nikita SMS: {e}")
        return False


def send_telegram_debug(text):
    """Дублирует OTP-код в тестовый Telegram-чат (TG_BOT_TOKEN/TG_CHAT_ID) —
    только для отладки при разработке, не влияет на основную отправку по SMS/email.
    Если не настроено — тихо ничего не делает (не ошибка, не блокирует основной поток)."""
    token = getattr(settings, 'TG_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TG_CHAT_ID', '')
    chat_id_2 = getattr(settings, 'TG_CHAT_ID_2', '')
    thread_id = getattr(settings, 'TG_CHAT_THREAD_ID', '')

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if thread_id:
        payload["message_thread_id"] = thread_id

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
        )
        data2 = json.dumps({"chat_id": chat_id_2, "text": text}).encode('utf-8')
        if chat_id_2:
            req2 = urllib.request.Request(
                url,
                data=data2,
                headers={'Content-Type': 'application/json'},
            )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read().decode('utf-8')
            logger.info(f"Telegram debug message sent. Response: {res_data}")
            if chat_id_2:
                with urllib.request.urlopen(req2, timeout=10) as response2:
                    res_data2 = response2.read().decode('utf-8')
                    logger.info(f"Telegram debug message sent to chat_id_2. Response: {res_data2}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        logger.error(f"Failed to send Telegram debug message: HTTP {e.code}: {body}")
        return False
    except Exception as e:
        logger.error(f"Failed to send Telegram debug message: {e}")
        return False



# Домен технических адресов: у пациента, зарегистрированного по телефону, нет
# почты, а User.email обязателен и уникален — туда пишется заглушка вида
# 996700111222@phone.imbir.kg. Показывать её человеку нельзя.
PHONE_PLACEHOLDER_DOMAIN = 'phone.imbir.kg'


def phone_digits(phone):
    """Только цифры номера: '+996 700 111 222' и '+996700111222' дают одно и то же."""
    return ''.join(c for c in (phone or '') if c.isdigit())


def is_placeholder_email(email):
    return bool(email) and email.lower().endswith('@' + PHONE_PLACEHOLDER_DOMAIN)


def public_email(email):
    """Email для ответа API: технический адрес-заглушку заменяем пустой строкой."""
    return '' if is_placeholder_email(email) else (email or '')


def make_phone_placeholder_email(phone, exclude_user_id=None):
    """Свободный технический email для номера.

    Обычно это <цифры>@phone.imbir.kg. Но заглушка может остаться занятой
    другим аккаунтом (он сменил телефон, а старый номер достался новому
    владельцу SIM) — тогда добавляем суффикс, иначе create_user падал на
    уникальности email с 500.
    """
    from users.models import User

    digits = phone_digits(phone) or 'user'
    qs = User.objects.all()
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    candidate = f'{digits}@{PHONE_PLACEHOLDER_DOMAIN}'
    n = 1
    while qs.filter(email__iexact=candidate).exists():
        n += 1
        candidate = f'{digits}.{n}@{PHONE_PLACEHOLDER_DOMAIN}'
    return candidate


def link_guest_appointments(user, phone=None, email=None):
    """Привязывает к аккаунту гостевые записи (patient=NULL) с тем же
    телефоном или email. Вызывать только после того, как владение контактом
    подтверждено кодом, — иначе чужие записи можно забрать, указав чужой номер.

    Телефон сравнивается по цифрам: гостевая форма шлёт '+996 700123456', а
    регистрация — '+996700123456'. Email — без учёта регистра.
    Возвращает число привязанных записей.
    """
    from appointments.models import Appointment

    ids = []
    digits = phone_digits(phone)
    if digits:
        # Номер всегда кончается цифрой — по ней грубо сужаем выборку в БД,
        # точное сравнение по цифрам делаем уже здесь.
        candidates = Appointment.objects.filter(
            patient__isnull=True, guest_phone__endswith=digits[-1],
        ).values_list('id', 'guest_phone')
        ids.extend(pk for pk, guest_phone in candidates if phone_digits(guest_phone) == digits)
    if email:
        ids.extend(
            Appointment.objects.filter(patient__isnull=True, guest_email__iexact=email.strip())
            .values_list('id', flat=True)
        )
    if not ids:
        return 0
    return Appointment.objects.filter(id__in=set(ids), patient__isnull=True).update(patient=user)


def clean_unique_phone(value, user=None):
    """Валидатор телефона при правке профиля: пустую строку храним как NULL
    (иначе два аккаунта с '' упираются в unique), а занятый другим аккаунтом
    номер — понятная 400 вместо IntegrityError и 500."""
    from rest_framework import serializers
    from users.models import User

    phone = (value or '').strip()
    if not phone:
        return None
    qs = User.objects.filter(phone=phone)
    if user is not None and user.pk:
        qs = qs.exclude(pk=user.pk)
    if qs.exists():
        raise serializers.ValidationError(User._meta.get_field('phone').error_messages['unique'])
    return phone


def sync_placeholder_email(user, old_phone):
    """После смены телефона перевыпускает технический email под новый номер,
    чтобы старая заглушка не держала прежний номер (на него потом не
    зарегистрироваться). Настоящую почту не трогает. True — email изменён."""
    if not is_placeholder_email(user.email) or not user.phone:
        return False
    if phone_digits(user.phone) == phone_digits(old_phone):
        return False
    user.email = make_phone_placeholder_email(user.phone, exclude_user_id=user.pk)
    return True
