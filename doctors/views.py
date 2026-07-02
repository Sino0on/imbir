import json
from django.db.models import Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter

from users.models import DoctorProfile
from core.pagination import StandardPagination
from .serializers import DoctorListSerializer, DoctorDetailSerializer


def _json_escape(value: str) -> str:
    # SQLite JSONField хранит кириллицу как unicode-escape, нужна конвертация перед icontains
    return json.dumps(value, ensure_ascii=True)[1:-1]


@extend_schema(
    parameters=[
        OpenApiParameter(name='search', type=str, description='Поиск по имени и специализации'),
        OpenApiParameter(name='city', type=str, description='Фильтр по городу'),
        OpenApiParameter(name='specialization', type=str, description='Фильтр по специализации'),
        OpenApiParameter(name='min_price', type=int, description='Минимальная цена приёма'),
        OpenApiParameter(name='max_price', type=int, description='Максимальная цена приёма'),
        OpenApiParameter(name='min_rating', type=float, description='Минимальный рейтинг (0–5)'),
        OpenApiParameter(name='is_online', type=bool, description='Принимает онлайн (true/false)'),
        OpenApiParameter(name='payment_method', type=str, description='Способ оплаты'),
    ],
    tags=['Doctors Catalog'],
    summary='Список врачей с фильтрацией',
    description='Возвращает список врачей с пагинацией и поддержкой фильтрации по различным параметрам.'
)
class DoctorListView(ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = DoctorListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = (
            DoctorProfile.objects
            .filter(user__is_active=True, is_published=True)
            .select_related('user')
            .order_by('-rating', '-reviews_count')
        )

        params = self.request.query_params

        search = params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(primary_specializations__icontains=_json_escape(search))
                | Q(narrow_specializations__icontains=_json_escape(search))
            )

        city = params.get('city', '').strip()
        if city:
            qs = qs.filter(city__icontains=city)

        specialization = params.get('specialization', '').strip()
        if specialization:
            escaped = _json_escape(specialization)
            qs = qs.filter(
                Q(primary_specializations__icontains=escaped)
                | Q(narrow_specializations__icontains=escaped)
            )

        min_price = params.get('min_price')
        if min_price:
            try:
                qs = qs.filter(consultation_price__gte=float(min_price))
            except ValueError:
                pass

        max_price = params.get('max_price')
        if max_price:
            try:
                qs = qs.filter(consultation_price__lte=float(max_price))
            except ValueError:
                pass

        min_rating = params.get('min_rating')
        if min_rating:
            try:
                qs = qs.filter(rating__gte=float(min_rating))
            except ValueError:
                pass

        is_online = params.get('is_online')
        if is_online is not None:
            qs = qs.filter(is_online_available=is_online.lower() in ('true', '1', 'yes'))

        payment_method = params.get('payment_method', '').strip()
        if payment_method:
            qs = qs.filter(payment_methods__icontains=_json_escape(payment_method))

        return qs


class DoctorDetailView(RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = DoctorDetailSerializer

    def get_object(self):
        from django.shortcuts import get_object_or_404
        # id в URL — это user.id, а не DoctorProfile.id
        return get_object_or_404(
            DoctorProfile.objects.select_related('user').filter(
                user__is_active=True, is_published=True
            ),
            user__id=self.kwargs['pk'],
        )


class DoctorAvailableSlotsView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[
            OpenApiParameter(name='date', type=str, description='Дата в формате YYYY-MM-DD', required=True),
        ],
        tags=['Doctors Catalog'],
        summary='Свободные слоты времени врача',
        description='Возвращает список 30-минутных интервалов с флагом доступности (available: true/false).'
    )
    def get(self, request, pk):
        from rest_framework.response import Response
        from rest_framework import status
        from django.shortcuts import get_object_or_404
        from datetime import datetime, timedelta
        from django.utils import timezone
        from appointments.models import Appointment

        doctor_profile = get_object_or_404(
            DoctorProfile.objects.select_related('user').filter(
                user__is_active=True, is_published=True
            ),
            user__id=pk,
        )
        date_str = request.query_params.get('date', '').strip()
        if not date_str:
            return Response({'detail': 'Параметр date обязателен (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

        # Helper to compute slots
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'detail': 'Некорректный формат даты. Используйте YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        # Locale-independent day name mapping
        DAYS_OF_WEEK = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        weekday_name = DAYS_OF_WEEK[target_date.weekday()]

        schedule = doctor_profile.schedule or {}
        day_schedule = schedule.get(weekday_name)

        if not day_schedule or not isinstance(day_schedule, dict):
            return Response({'date': date_str, 'slots': []})

        if not day_schedule.get('enabled', True):
            return Response({'date': date_str, 'slots': []})

        start_str = day_schedule.get('from') or day_schedule.get('start')
        end_str = day_schedule.get('to') or day_schedule.get('end')

        if not start_str or not end_str:
            return Response({'date': date_str, 'slots': []})

        try:
            start_time = datetime.strptime(start_str, '%H:%M').time()
            end_time = datetime.strptime(end_str, '%H:%M').time()
        except ValueError:
            return Response({'date': date_str, 'slots': []})

        booked_times = set(
            Appointment.objects.filter(
                doctor=doctor_profile,
                date=target_date,
                status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED, Appointment.Status.COMPLETED]
            ).values_list('time', flat=True)
        )

        lunch = doctor_profile.lunch_break or {}
        lunch_start = None
        lunch_end = None

        lunch_start_str = lunch.get('from') or lunch.get('start')
        lunch_end_str = lunch.get('to') or lunch.get('end')

        if lunch_start_str and lunch_end_str:
            try:
                lunch_start = datetime.strptime(lunch_start_str, '%H:%M').time()
                lunch_end = datetime.strptime(lunch_end_str, '%H:%M').time()
            except ValueError:
                pass

        slots = []
        current_dt = datetime.combine(target_date, start_time)
        end_dt = datetime.combine(target_date, end_time)

        local_now = timezone.localtime(timezone.now())
        local_today = local_now.date()
        local_time = local_now.time()

        while current_dt < end_dt:
            slot_time = current_dt.time()
            available = True

            if slot_time in booked_times:
                available = False

            if available and lunch_start and lunch_end:
                if lunch_start <= slot_time < lunch_end:
                    available = False

            if available and target_date < local_today:
                available = False
            elif available and target_date == local_today:
                if slot_time <= local_time:
                    available = False

            slots.append({
                'time': slot_time.strftime('%H:%M'),
                'available': available
            })

            current_dt += timedelta(minutes=30)

        return Response({'date': date_str, 'slots': slots})
