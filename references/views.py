from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from users.models import DoctorProfile, ClinicProfile


def _flat_json_field(*pairs):
    """Collect unique non-empty strings from JSONField list-columns across multiple querysets."""
    values = set()
    for qs, field in pairs:
        for row in qs.values_list(field, flat=True):
            if row:
                values.update(v for v in row if v)
    return sorted(values)


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


@extend_schema(**_REF_SCHEMA, summary='Список специализаций')
class SpecializationsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        doctor_qs = DoctorProfile.objects.filter(is_published=True)
        clinic_qs = ClinicProfile.objects.filter(is_published=True)
        data = _flat_json_field(
            (doctor_qs, 'primary_specializations'),
            (doctor_qs, 'narrow_specializations'),
            (clinic_qs, 'primary_specializations'),
            (clinic_qs, 'narrow_specializations'),
        )
        return Response({'data': data})


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
        })
    )
})


@extend_schema(responses={200: _COUNTRY_CODES_RESPONSE}, tags=['References'], summary='Список телефонных кодов стран')
class CountryCodesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({'data': COUNTRY_CODES})
