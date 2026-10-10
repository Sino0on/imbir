from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter

from users.models import DoctorProfile, ClinicProfile
from services.models import Service
from services.views import VISIBLE_CLINIC_Q

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


CITY_PARAMETER = OpenApiParameter(
    name='city', type=str,
    description='Город (необязательно). Без параметра или all — по всем городам.',
)


# Сколько слов запроса учитываем: на каждое слово — свой подзапрос, слишком
# длинная строка иначе раздувала бы SQL.
MAX_SEARCH_WORDS = 5


def filter_doctors_by_search(qs, query):
    """Поиск врачей по ФИО и специализации. Запрос делится на слова, и каждое
    слово должно найтись (И) хотя бы в одном из полей (ИЛИ): фамилии, имени,
    отчестве или названии специализации. Раньше вся строка целиком сравнивалась
    с каждым полем по отдельности, и «Иванов Иван» не находил никого, а по
    отчеству не искали вовсе.

    Специализации проверяются подзапросом, а не JOIN'ом: иначе на каждое слово
    добавлялись бы свои JOIN'ы по M2M и строки размножались."""
    for word in query.split()[:MAX_SEARCH_WORDS]:
        spec_match = DoctorProfile.objects.filter(
            Q(primary_specializations__name__icontains=word)
            | Q(narrow_specializations__name__icontains=word)
        ).values('pk')
        qs = qs.filter(
            Q(user__last_name__icontains=word)
            | Q(user__first_name__icontains=word)
            | Q(user__patronymic__icontains=word)
            | Q(pk__in=spec_match)
        )
    return qs


def filter_clinics_by_search(qs, query):
    """Поиск клиник по названию и по специализациям: раньше искали только по
    названию, и запрос «Кардиология» не находил ни одной клиники."""
    spec_match = ClinicProfile.objects.filter(
        Q(primary_specializations__name__icontains=query)
        | Q(narrow_specializations__name__icontains=query)
    ).values('pk')
    return qs.filter(Q(name__icontains=query) | Q(pk__in=spec_match))


def _get_city(request):
    """Город из ?city= — тот, что выбрал пользователь. Город по IP здесь не
    подставляем: без параметра поиск, как и раньше, идёт по всем городам."""
    city = request.query_params.get('city', '').strip()
    return '' if city.lower() == 'all' else city


def _filter_by_city(doctors, clinics, services, city):
    if not city:
        return doctors, clinics, services
    return (
        doctors.filter(city__icontains=city),
        clinics.filter(city__icontains=city),
        # Город услуги — город клиники, у частной услуги — город врача.
        services.filter(
            Q(clinic__city__icontains=city)
            | Q(clinic__isnull=True, doctors__city__icontains=city)
        ).distinct(),
    )


class GlobalSearchSuggestView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[
            OpenApiParameter(name='q', type=str, description='Поисковый запрос (ФИО врача, специализация, название клиники или услуги)', required=True),
            CITY_PARAMETER,
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

        # Search doctors
        doctors = DoctorProfile.objects.filter(
            user__is_active=True,
            is_published=True
        ).select_related('user')
        doctors = filter_doctors_by_search(doctors, query)

        # Search clinics (по названию и специализациям)
        clinics = filter_clinics_by_search(
            ClinicProfile.objects.filter(user__is_active=True, is_published=True),
            query,
        )

        # Search services (услуги скрытых клиник не показываем)
        services = Service.objects.filter(
            VISIBLE_CLINIC_Q, is_active=True
        ).filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(description__icontains=query)
        )

        doctors, clinics, services = _filter_by_city(
            doctors, clinics, services, _get_city(request)
        )
        doctors, clinics, services = doctors[:5], clinics[:5], services[:5]

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
            CITY_PARAMETER,
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

        # Search doctors
        doctors = DoctorProfile.objects.filter(
            user__is_active=True,
            is_published=True
        ).select_related('user')
        doctors = filter_doctors_by_search(doctors, query)

        # Search clinics (по названию и специализациям)
        clinics = filter_clinics_by_search(
            ClinicProfile.objects.filter(user__is_active=True, is_published=True),
            query,
        )

        # Search services (услуги скрытых клиник не показываем)
        services = Service.objects.filter(
            VISIBLE_CLINIC_Q, is_active=True
        ).select_related('clinic', 'branch').prefetch_related('doctors__user').filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(description__icontains=query)
        )

        doctors, clinics, services = _filter_by_city(
            doctors, clinics, services, _get_city(request)
        )
        doctors, clinics, services = doctors[:20], clinics[:20], services[:20]

        return Response({
            "doctors": DoctorListSerializer(doctors, many=True, context={'request': request}).data,
            "clinics": ClinicListSerializer(clinics, many=True, context={'request': request}).data,
            "services": ServiceListSerializer(services, many=True, context={'request': request}).data
        })
