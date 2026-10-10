"""Общие помощники нормализации и проверки пользовательского ввода.

Используются в регистрации клиники и в PUT профиля клиники, чтобы одни и те же
значения (сайт без схемы, координаты из Google Maps) принимались одинаково.
"""
import os
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import SuspiciousFileOperation, ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.utils.text import get_valid_filename
from rest_framework import serializers

# Модельные latitude/longitude — DecimalField(max_digits=9, decimal_places=6).
COORDINATE_MAX_DIGITS = 9
COORDINATE_DECIMAL_PLACES = 6
_COORDINATE_QUANT = Decimal(1).scaleb(-COORDINATE_DECIMAL_PLACES)

# FileField по умолчанию max_length=100: '<папка>/<uuid32>/' занимает ~51 символ.
_DOCUMENT_NAME_MAX_LENGTH = 45

WEBSITE_ERROR = 'Введите правильный адрес сайта, например https://example.kg'
# Схема в начале адреса («https://»); «://» внутри query-строки схемой не считается
_URL_SCHEME_RE = re.compile(r'^[a-z][a-z0-9+.-]*://', re.IGNORECASE)


def normalize_website(value):
    """Добавляет https:// к сайту без схемы («imbir.kg» → «https://imbir.kg»)
    и проверяет результат как URL. Пустое значение возвращается как ''.
    Бросает django ValidationError, если адрес некорректен."""
    value = (value or '').strip()
    if not value:
        return ''
    if not _URL_SCHEME_RE.match(value):
        value = f'https://{value.lstrip("/")}'
    URLValidator()(value)
    return value


def round_coordinate(value):
    """Округляет координату до 6 знаков после запятой (Google Maps отдаёт 14).
    None/'' → None. Бросает ValueError на нечисловое значение."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError(value)
    if not number.is_finite():
        raise ValueError(value)
    return number.quantize(_COORDINATE_QUANT, rounding=ROUND_HALF_UP)


class WebsiteField(serializers.CharField):
    """Сайт: принимает адрес без схемы и дописывает https://."""

    def __init__(self, **kwargs):
        kwargs.setdefault('max_length', 200)
        kwargs.setdefault('allow_blank', True)
        kwargs.setdefault('required', False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            value = normalize_website(value)
        except DjangoValidationError:
            raise serializers.ValidationError(WEBSITE_ERROR)
        if self.max_length is not None and len(value) > self.max_length:
            raise serializers.ValidationError(WEBSITE_ERROR)
        return value


class CoordinateField(serializers.DecimalField):
    """Широта/долгота: лишние знаки после запятой округляются, а не дают 400.
    Пустая строка (очищенное поле формы) трактуется как null."""

    def __init__(self, **kwargs):
        kwargs.setdefault('max_digits', COORDINATE_MAX_DIGITS)
        kwargs.setdefault('decimal_places', COORDINATE_DECIMAL_PLACES)
        kwargs.setdefault('required', False)
        kwargs.setdefault('allow_null', True)
        super().__init__(**kwargs)

    def run_validation(self, data=serializers.empty):
        if self.allow_null and isinstance(data, str) and not data.strip():
            data = None
        return super().run_validation(data)

    def validate_precision(self, value):
        value = value.quantize(Decimal(1).scaleb(-self.decimal_places), rounding=ROUND_HALF_UP)
        return super().validate_precision(value)


def _safe_filename_part(value):
    try:
        return get_valid_filename(value)
    except SuspiciousFileOperation:  # имя из одних спецсимволов
        return ''


def document_upload_path(folder, uploaded_file):
    """Путь для загружаемого документа: '<folder>/<uuid>/<исходное имя>'.
    Уникальность даёт папка-uuid, а последний сегмент URL остаётся исходным
    именем файла — по нему пользователь отличает документы друг от друга."""
    name = os.path.basename(uploaded_file.name or '')
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    stem = _safe_filename_part(stem)
    ext = _safe_filename_part(ext.lstrip('.'))[:10]
    if ext:
        ext = f'.{ext}'
    stem = stem[:max(_DOCUMENT_NAME_MAX_LENGTH - len(ext), 1)] or 'document'
    return f'{folder.rstrip("/")}/{uuid.uuid4().hex}/{stem}{ext}'
