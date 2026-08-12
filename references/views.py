from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from users.models import DoctorProfile, ClinicProfile, User
from services.models import Service
from reviews.models import Review
from .models import Specialization, SiteSettings, AccountStatus
from .serializers import SpecializationSerializer, SiteSettingsSerializer, AccountStatusSerializer


# Тестовый мусор, попавший в прод. Реальная чистка — через админку;
# здесь отсекаем на уровне API, чтобы не показывать пользователям.
_JUNK_VALUES = {'das', 'test', 'тест', 'therapist', 'string', 'qwe', 'asd'}


def _flat_json_field(*pairs):
    """Collect unique non-empty strings from JSONField list-columns across multiple querysets."""
    values = set()
    for qs, field in pairs:
        for row in qs.values_list(field, flat=True):
            if row:
                values.update(v for v in row if v)
    return _clean_values(values)


def _clean_values(values):
    """Отсекает тестовый мусор и дедуплицирует значения без учёта регистра."""
    canonical = {}
    for v in values:
        v = (v or '').strip()
        if not v:
            continue
        key = v.casefold()
        if key in _JUNK_VALUES:
            continue
        canonical.setdefault(key, v)
    return sorted(canonical.values(), key=str.casefold)


_REF_RESPONSE = inline_serializer('ReferenceList', fields={
    'data': serializers.ListField(child=serializers.CharField()),
})
_REF_SCHEMA = dict(responses={200: _REF_RESPONSE}, tags=['References'])


@extend_schema(**_REF_SCHEMA, summary='Список городов')
class CitiesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        cities = set()
        cities.update(
            DoctorProfile.objects.filter(is_published=True)
            .exclude(city='').values_list('city', flat=True)
        )
        cities.update(
            ClinicProfile.objects.filter(is_published=True)
            .exclude(city='').values_list('city', flat=True)
        )
        return Response({'data': sorted(cities)})


_SPEC_RESPONSE = inline_serializer('SpecializationList', fields={
    'data': SpecializationSerializer(many=True),
})


@extend_schema(responses={200: _SPEC_RESPONSE}, tags=['References'], summary='Список специализаций')
class SpecializationsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        # ?type=clinic — специализации, встречающиеся у клиник,
        # ?type=doctor — только у врачей,
        # без параметра — объединение обоих (обратная совместимость).
        ref_type = request.query_params.get('type', '').strip().lower()

        filters = Q()
        if ref_type != 'clinic':
            filters |= Q(doctors_primary__is_published=True) | Q(doctors_narrow__is_published=True)
        if ref_type != 'doctor':
            filters |= Q(clinics_primary__is_published=True) | Q(clinics_narrow__is_published=True)

        specializations = Specialization.objects.filter(filters).distinct().order_by('name')
        serializer = SpecializationSerializer(specializations, many=True, context={'request': request})
        return Response({'data': serializer.data})


@extend_schema(**_REF_SCHEMA, summary='Типы клиник')
class ClinicTypesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        types = list(
            ClinicProfile.objects.filter(is_published=True)
            .exclude(clinic_type='')
            .values_list('clinic_type', flat=True)
            .distinct()
            .order_by('clinic_type')
        )
        return Response({'data': types})


@extend_schema(**_REF_SCHEMA, summary='Список категорий услуг')
class ServiceCategoriesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        categories = list(
            Service.objects.filter(is_active=True)
            .exclude(category='')
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        return Response({'data': categories})


@extend_schema(**_REF_SCHEMA, summary='Список языков')
class LanguagesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        data = _flat_json_field(
            (DoctorProfile.objects.filter(is_published=True), 'languages'),
        )
        return Response({'data': data})


@extend_schema(**_REF_SCHEMA, summary='Список оборудования')
class EquipmentView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        data = _flat_json_field(
            (DoctorProfile.objects.filter(is_published=True), 'equipment'),
            (ClinicProfile.objects.filter(is_published=True), 'equipment'),
        )
        return Response({'data': data})


@extend_schema(**_REF_SCHEMA, summary='Условия для пациентов')
class ConditionsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        data = _flat_json_field(
            (DoctorProfile.objects.filter(is_published=True), 'patient_conditions'),
            (ClinicProfile.objects.filter(is_published=True), 'patient_conditions'),
        )
        return Response({'data': data})


@extend_schema(**_REF_SCHEMA, summary='Способы оплаты')
class PaymentMethodsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        data = _flat_json_field(
            (DoctorProfile.objects.filter(is_published=True), 'payment_methods'),
            (ClinicProfile.objects.filter(is_published=True), 'payment_methods'),
        )
        return Response({'data': data})


import os
import json
from django.conf import settings

COUNTRY_CODES = []
json_path = os.path.join(settings.BASE_DIR, 'references', 'country_codes.json')
if os.path.exists(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            COUNTRY_CODES = json.load(f)
    except Exception:
        pass

_COUNTRY_CODES_RESPONSE = inline_serializer('CountryCodeList', fields={
    'data': serializers.ListField(
        child=inline_serializer('CountryCodeItem', fields={
            'code': serializers.CharField(),
            'country': serializers.CharField(),
            'flag': serializers.CharField(),
            'iso': serializers.CharField(),
            'length': serializers.IntegerField(),
        })
    )
})


@extend_schema(responses={200: _COUNTRY_CODES_RESPONSE}, tags=['References'], summary='Список телефонных кодов стран')
class CountryCodesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({'data': COUNTRY_CODES})


_SITE_SETTINGS_RESPONSE = inline_serializer('SiteSettingsResponse', fields={
    'data': SiteSettingsSerializer(),
})


@extend_schema(
    responses={200: _SITE_SETTINGS_RESPONSE}, tags=['References'],
    summary='Настройки сайта (соцсети, контакты, юридические тексты для футера)',
)
class SiteSettingsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({'data': SiteSettingsSerializer(SiteSettings.load()).data})


_USER_STATUS_RESPONSE = inline_serializer('UserAccountStatusResponse', fields={
    'data': inline_serializer('UserAccountStatusData', fields={
        'user_id': serializers.IntegerField(),
        'reviews_count': serializers.IntegerField(),
        'average_rating': serializers.FloatField(allow_null=True),
        'percent': serializers.FloatField(allow_null=True),
        'status': AccountStatusSerializer(allow_null=True),
    }),
})


@extend_schema(
    responses={200: _USER_STATUS_RESPONSE}, tags=['References'],
    summary='Статус пользователя по среднему рейтингу оставленных им отзывов',
    description=(
        'Средний рейтинг звёзд по всем отзывам, написанным пользователем, переводится '
        'в проценты (avg/5*100) и сопоставляется с ближайшим по убыванию порогом из '
        'справочника AccountStatus.percent. Например, средний рейтинг 5.0 → 100% → '
        'статус с percent=90 ("Витамин С" в текущем справочнике), а 25% → статус '
        'с percent=10 ("Острый Скальпель"). Если у пользователя нет ни одного '
        'отзыва — status будет null.'
    ),
)
class UserAccountStatusView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, user_id):
        get_object_or_404(User, pk=user_id)

        agg = Review.objects.filter(author_id=user_id).aggregate(
            avg_rating=Avg('rating'), count=Count('id'),
        )
        reviews_count = agg['count'] or 0
        avg_rating = agg['avg_rating']

        if not reviews_count or avg_rating is None:
            return Response({'data': {
                'user_id': user_id,
                'reviews_count': 0,
                'average_rating': None,
                'percent': None,
                'status': None,
            }})

        percent = round(float(avg_rating) / 5 * 100, 2)
        account_status = AccountStatus.objects.filter(percent__lte=percent).order_by('-percent').first()

        return Response({'data': {
            'user_id': user_id,
            'reviews_count': reviews_count,
            'average_rating': round(float(avg_rating), 2),
            'percent': percent,
            'status': (
                AccountStatusSerializer(account_status, context={'request': request}).data
                if account_status else None
            ),
        }})
