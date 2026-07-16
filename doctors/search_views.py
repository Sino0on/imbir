import json
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter

from users.models import DoctorProfile, ClinicProfile
from services.models import Service

# Import suggest serializers
from doctors.search_serializers import (
    SuggestDoctorSerializer,
    SuggestClinicSerializer,
    SuggestServiceSerializer
)

# Import list serializers for extended results
from doctors.serializers import DoctorListSerializer
from clinics.serializers import ClinicListSerializer
from services.serializers import ServiceListSerializer


def _json_escape(value: str) -> str:
    # SQLite JSONField stores Cyrillic as unicode-escape sequences
    return json.dumps(value, ensure_ascii=True)[1:-1]


class GlobalSearchSuggestView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[
            OpenApiParameter(name='q', type=str, description='Поисковый запрос (ФИО врача, специализация, название клиники или услуги)', required=True),
        ],
        tags=['Global Search'],
        summary='Быстрый автокомплит-поиск (короткий ответ)',
        description='Возвращает до 5 наиболее подходящих врачей, клиник и услуг по ключевому слову.'
    )
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            query = request.query_params.get('search', '').strip()

        if not query:
            return Response({
                "doctors": [],
                "clinics": [],
                "services": []
            })

        escaped_query = _json_escape(query)

        # Search doctors
        doctors = DoctorProfile.objects.filter(
            user__is_active=True, 
            is_published=True
        ).select_related('user').filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(primary_specializations__icontains=escaped_query)
            | Q(narrow_specializations__icontains=escaped_query)
        )[:5]

        # Search clinics
        clinics = ClinicProfile.objects.filter(
            user__is_active=True, 
            is_published=True
        ).filter(
            name__icontains=query
        )[:5]

        # Search services
        services = Service.objects.filter(
            is_active=True
        ).filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(description__icontains=query)
        )[:5]

        return Response({
            "doctors": SuggestDoctorSerializer(doctors, many=True, context={'request': request}).data,
            "clinics": SuggestClinicSerializer(clinics, many=True, context={'request': request}).data,
            "services": SuggestServiceSerializer(services, many=True, context={'request': request}).data
        })


class GlobalSearchView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[
            OpenApiParameter(name='q', type=str, description='Поисковый запрос (ФИО врача, специализация, название клиники или услуги)', required=True),
        ],
        tags=['Global Search'],
        summary='Расширенный глобальный поиск (подробный ответ)',
        description='Возвращает список подходящих врачей, клиник и услуг с полным набором данных.'
    )
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            query = request.query_params.get('search', '').strip()

        if not query:
            return Response({
                "doctors": [],
                "clinics": [],
                "services": []
            })

        escaped_query = _json_escape(query)

        # Search doctors
        doctors = DoctorProfile.objects.filter(
            user__is_active=True, 
            is_published=True
        ).select_related('user').filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(primary_specializations__icontains=escaped_query)
            | Q(narrow_specializations__icontains=escaped_query)
        )[:20]

        # Search clinics
        clinics = ClinicProfile.objects.filter(
            user__is_active=True, 
            is_published=True
        ).filter(
            name__icontains=query
        )[:20]

        # Search services
        services = Service.objects.filter(
            is_active=True
        ).select_related('clinic').prefetch_related('doctors__user').filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(description__icontains=query)
        )[:20]

        return Response({
            "doctors": DoctorListSerializer(doctors, many=True, context={'request': request}).data,
            "clinics": ClinicListSerializer(clinics, many=True, context={'request': request}).data,
            "services": ServiceListSerializer(services, many=True, context={'request': request}).data
        })
