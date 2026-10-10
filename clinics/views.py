from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from users.models import ClinicProfile
from core.pagination import StandardPagination
from doctors.search_views import filter_clinics_by_search
from doctors.views import BaseProfileViewView
from services.models import Service
from .serializers import ClinicListSerializer, ClinicDetailSerializer


@extend_schema(
    parameters=[
        OpenApiParameter(name='search', type=str, description='Поиск по названию клиники'),
        OpenApiParameter(name='city', type=str, description='Фильтр по городу; all — все города'),
        OpenApiParameter(
            name='specialization',
            type=str,
            description=(
                'Фильтр по специализации. Несколько значений — через запятую '
                '(например, specialization=Кардиология,Терапия) или повтором параметра; '
                'клиника попадает в выдачу, если совпадает хотя бы одна.'
            ),
        ),
        OpenApiParameter(name='min_rating', type=float, description='Минимальный рейтинг (0–5)'),
        OpenApiParameter(name='min_experience', type=int, description='Минимальный стаж клиники (лет)'),
        OpenApiParameter(name='max_experience', type=int, description='Максимальный стаж клиники (лет)'),
        OpenApiParameter(name='min_price', type=float, description='Минимальная цена услуги'),
        OpenApiParameter(name='max_price', type=float, description='Максимальная цена услуги'),
    ],
    tags=['Clinics Catalog'],
    summary='Список клиник с фильтрацией',
    description='Возвращает список опубликованных клиник с пагинацией и фильтрацией.',
)
class ClinicListView(ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ClinicListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = (
            ClinicProfile.objects
            .filter(user__is_active=True, is_published=True)
            .select_related('user')
            # id — уникальный хвост сортировки, см. DoctorListView: без него
            # «Показать ещё» дублировало и пропускало клиники.
            .order_by('-rating', '-reviews_count', 'id')
        )

        params = self.request.query_params

        search = params.get('search', '').strip()
        if search:
            qs = filter_clinics_by_search(qs, search)

        # city=all — явно «все города»: без фильтра и без подстановки города,
        # определённого middleware по IP. Без параметра city — как раньше.
        city = params.get('city', '').strip()
        if city.lower() == 'all':
            city = ''
        elif not city and hasattr(self.request, 'city'):
            city = self.request.city
        if city:
            qs = qs.filter(city__icontains=city)

        specialization_values = []
        for raw in params.getlist('specialization'):
            specialization_values.extend(
                value.strip() for value in raw.split(',') if value.strip()
            )
        specialization_values = list(dict.fromkeys(specialization_values))

        if specialization_values:
            # Точное совпадение названия из справочника, а не подстрока —
            # см. DoctorListView.
            specialization_filter = Q()
            for value in specialization_values:
                specialization_filter |= (
                    Q(primary_specializations__name__iexact=value)
                    | Q(narrow_specializations__name__iexact=value)
                )
            qs = qs.filter(specialization_filter).distinct()

        min_rating = params.get('min_rating')
        if min_rating:
            try:
                qs = qs.filter(rating__gte=float(min_rating))
            except ValueError:
                pass

        min_experience = params.get('min_experience')
        if min_experience:
            try:
                qs = qs.filter(experience_years__gte=int(min_experience))
            except ValueError:
                pass

        max_experience = params.get('max_experience')
        if max_experience:
            try:
                qs = qs.filter(experience_years__lte=int(max_experience))
            except ValueError:
                pass

        # Оба края диапазона — условия на одну и ту же активную услугу. Раньше
        # это были два отдельных .filter() по связи «многие»: клиника с услугами
        # за 100 и за 10 000 проходила фильтр 500–1000, хотя услуги в нём нет;
        # учитывались и отключённые услуги.
        price_filter = {}
        min_price = params.get('min_price')
        if min_price:
            try:
                price_filter['price__gte'] = float(min_price)
            except ValueError:
                pass

        max_price = params.get('max_price')
        if max_price:
            try:
                price_filter['price__lte'] = float(max_price)
            except ValueError:
                pass

        if price_filter:
            qs = qs.filter(pk__in=Service.objects.filter(
                is_active=True, clinic__isnull=False, **price_filter,
            ).values('clinic_id'))

        return qs


class ClinicDetailView(RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ClinicDetailSerializer

    def get_object(self):
        from django.shortcuts import get_object_or_404
        obj = get_object_or_404(
            ClinicProfile.objects
            .select_related('user')
            .prefetch_related('photos')
            .filter(user__is_active=True, is_published=True),
            user__id=self.kwargs['pk'],
        )
        # Просмотр засчитывается не здесь, а в ClinicProfileViewView — см.
        # DoctorDetailView.
        return obj


@extend_schema(
    request=None, responses={204: None},
    tags=['Clinics Catalog'], summary='Засчитать просмотр страницы клиники',
)
class ClinicProfileViewView(BaseProfileViewView):
    profile_kind = 'clinic'
    model = ClinicProfile
