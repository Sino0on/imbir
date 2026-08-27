import os
import re

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.db.models import F, Q
from django.shortcuts import redirect, render
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer

from users.models import DoctorProfile
from core.pagination import StandardPagination
from .models import Interview
from .serializers import DoctorListSerializer, DoctorDetailSerializer, PublicInterviewSerializer


@extend_schema(
    parameters=[
        OpenApiParameter(name='search', type=str, description='Поиск по имени и специализации'),
        OpenApiParameter(name='city', type=str, description='Фильтр по городу'),
        OpenApiParameter(
            name='specialization', type=str,
            description='Фильтр по специализации. Несколько значений — через запятую '
                        '(?specialization=Кардиолог,Терапевт) или повтором параметра; '
                        'врач попадает в выдачу, если совпадает хотя бы одна.',
        ),
        OpenApiParameter(name='min_price', type=int, description='Минимальная цена приёма'),
        OpenApiParameter(name='max_price', type=int, description='Максимальная цена приёма'),
        OpenApiParameter(name='min_rating', type=float, description='Минимальный рейтинг (0–5)'),
        OpenApiParameter(name='is_online', type=bool, description='Принимает онлайн (true/false)'),
        OpenApiParameter(name='payment_method', type=str, description='Способ оплаты'),
        OpenApiParameter(name='min_experience', type=int, description='Минимальный стаж (лет)'),
        OpenApiParameter(name='max_experience', type=int, description='Максимальный стаж (лет)'),
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
                | Q(primary_specializations__name__icontains=search)
                | Q(narrow_specializations__name__icontains=search)
            ).distinct()

        city = params.get('city', '').strip()
        if not city and hasattr(self.request, 'city'):
            city = self.request.city
        if city:
            qs = qs.filter(city__icontains=city)

        specialization_values = []
        for raw in params.getlist('specialization'):
            specialization_values.extend(v.strip() for v in raw.split(',') if v.strip())
        specialization_values = list(dict.fromkeys(specialization_values))

        if specialization_values:
            spec_filter = Q()
            for value in specialization_values:
                spec_filter |= (
                    Q(primary_specializations__name__icontains=value)
                    | Q(narrow_specializations__name__icontains=value)
                )
            qs = qs.filter(spec_filter).distinct()

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

        is_online = params.get('is_online')
        if is_online is not None:
            qs = qs.filter(is_online_available=is_online.lower() in ('true', '1', 'yes'))

        payment_method = params.get('payment_method', '').strip()
        if payment_method:
            qs = qs.filter(payment_methods__icontains=payment_method)

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

        return qs


class DoctorDetailView(RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = DoctorDetailSerializer

    def get_object(self):
        from django.shortcuts import get_object_or_404
        # id в URL — это user.id, а не DoctorProfile.id
        obj = get_object_or_404(
            DoctorProfile.objects.select_related('user').filter(
                user__is_active=True, is_published=True
            ),
            user__id=self.kwargs['pk'],
        )
        DoctorProfile.objects.filter(pk=obj.pk).update(profile_views=F('profile_views') + 1)
        obj.profile_views += 1
        return obj


@extend_schema(tags=['Doctors Catalog'], summary='Список видео-интервью врачей')
class InterviewListView(ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = PublicInterviewSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            Interview.objects
            .filter(doctor__user__is_active=True, doctor__is_published=True)
            .select_related('doctor__user')
            .prefetch_related('doctor__primary_specializations')
            .order_by('-priority', 'id')
        )


def _normalize_photo_name(filename):
    """"Иванов Иван Иванович (2).jpg" -> "иванов иван иванович"."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)
    name = re.sub(r'\s+', ' ', name).strip().lower()
    return name


def _build_doctor_name_index():
    """{нормализованное ФИО: [DoctorProfile, ...]} по всем вариантам, под которыми
    может быть названо фото — "Фамилия Имя Отчество" или просто "Имя Отчество"."""
    index = {}
    for doctor in DoctorProfile.objects.select_related('user').all():
        last = (doctor.user.last_name or '').strip().lower()
        first = (doctor.user.first_name or '').strip().lower()
        patronymic = (doctor.user.patronymic or '').strip().lower()

        variants = set()
        if last and first and patronymic:
            variants.add(f"{last} {first} {patronymic}")
        if first and patronymic:
            variants.add(f"{first} {patronymic}")
        if last and first:
            variants.add(f"{last} {first}")

        for variant in variants:
            index.setdefault(variant, []).append(doctor)

    return index


def _match_and_apply_photos(files):
    """Сопоставляет каждый файл с врачом по имени и сразу сохраняет фото при
    однозначном совпадении. Общая логика для API-эндпоинта и HTML-инструмента."""
    name_index = _build_doctor_name_index()
    matched, not_found, ambiguous = [], [], []

    for file in files:
        key = _normalize_photo_name(file.name)
        candidates = name_index.get(key, [])

        if len(candidates) == 1:
            doctor = candidates[0]
            doctor.photo = file
            doctor.save(update_fields=['photo'])
            matched.append({
                'file': file.name,
                'doctor_id': doctor.user_id,
                'doctor_name': ' '.join(filter(None, [
                    doctor.user.last_name, doctor.user.first_name, doctor.user.patronymic,
                ])),
            })
        elif len(candidates) == 0:
            not_found.append(file.name)
        else:
            ambiguous.append({
                'file': file.name,
                'candidate_doctor_ids': [d.user_id for d in candidates],
            })

    return {'matched': matched, 'not_found': not_found, 'ambiguous': ambiguous}


@extend_schema(
    request={
        'multipart/form-data': inline_serializer('BulkDoctorPhotoUploadRequest', fields={
            'photos': serializers.ListField(
                child=serializers.ImageField(),
                help_text='Несколько файлов. Имя файла (без расширения) — '
                          '"Фамилия Имя Отчество" или "Имя Отчество".',
            ),
        }),
    },
    responses={200: inline_serializer('BulkDoctorPhotoUploadResponse', fields={
        'data': inline_serializer('BulkDoctorPhotoUploadResult', fields={
            'matched': serializers.ListField(child=serializers.DictField()),
            'not_found': serializers.ListField(child=serializers.CharField()),
            'ambiguous': serializers.ListField(child=serializers.DictField()),
        }),
    })},
    tags=['Doctors Catalog'],
    summary='Массовая загрузка аватарок врачей по имени файла',
    description=(
        'Только для админов. Принимает сразу несколько файлов в поле "photos". '
        'По имени файла (без расширения) ищется врач: "Фамилия Имя Отчество" или '
        '"Имя Отчество" (без фамилии). Совпал ровно один врач — фото проставляется '
        'ему. Ноль совпадений или несколько разных врачей под одним именем — файл '
        'пропускается (not_found / ambiguous), чтобы не перепутать фото.'
    ),
)
class BulkDoctorPhotoUploadView(APIView):
    permission_classes = (IsAdminUser,)
    parser_classes = (MultiPartParser,)

    def post(self, request):
        files = request.FILES.getlist('photos')
        if not files:
            return Response(
                {'detail': 'Передайте хотя бы один файл в поле "photos"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = _match_and_apply_photos(files)
        return Response({'data': result})


class DoctorAvailableSlotsView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[
            OpenApiParameter(name='date', type=str, description='Дата в формате YYYY-MM-DD', required=True),
            OpenApiParameter(
                name='service_id', type=int, required=False,
                description=(
                    'ID услуги, на которую записывается пациент. Если передан, слот считается '
                    'доступным только если под всю длительность ЭТОЙ услуги есть свободное окно '
                    '(иначе используется дефолт в 30 минут).'
                ),
            ),
        ],
        tags=['Doctors Catalog'],
        summary='Свободные слоты времени врача',
        description=(
            'Возвращает список 30-минутных интервалов с флагом доступности (available: true/false). '
            'Слот занят, если пересекается с интервалом [время, время + длительность услуги) '
            'уже существующей записи — длительность берётся из услуги каждой записи '
            '(30 минут по умолчанию, если услуга не указана).'
        ),
    )
    def get(self, request, pk):
        from rest_framework.response import Response
        from rest_framework import status
        from django.shortcuts import get_object_or_404
        from datetime import datetime, timedelta
        from django.utils import timezone
        from appointments.models import Appointment
        from appointments.utils import appointment_duration_minutes, appointment_time_range
        from services.models import Service

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

        busy_ranges = [
            appointment_time_range(apt.date, apt.time, apt.service)
            for apt in Appointment.objects.filter(
                doctor=doctor_profile,
                date=target_date,
                status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED, Appointment.Status.COMPLETED],
            ).select_related('service')
        ]

        service_id = request.query_params.get('service_id', '').strip()
        requested_service = Service.objects.filter(id=service_id).first() if service_id else None
        requested_duration = appointment_duration_minutes(requested_service)

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
            slot_end_dt = current_dt + timedelta(minutes=requested_duration)

            # Вся длительность услуги должна помещаться в рабочие часы врача.
            if slot_end_dt > end_dt:
                available = False

            if available and any(
                current_dt < busy_end and busy_start < slot_end_dt
                for busy_start, busy_end in busy_ranges
            ):
                available = False

            if available and lunch_start and lunch_end:
                lunch_start_dt = datetime.combine(target_date, lunch_start)
                lunch_end_dt = datetime.combine(target_date, lunch_end)
                if current_dt < lunch_end_dt and lunch_start_dt < slot_end_dt:
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


def bulk_photo_tool(request):
    """Внутренний инструмент: HTML-страница с логином, где можно за раз загрузить
    пачку фото врачей — они сами разложатся по врачам по имени файла."""
    if request.method == 'POST' and 'logout' in request.POST:
        auth_logout(request)
        return redirect('doctor-bulk-photo-tool')

    if request.method == 'POST' and 'photos' not in request.FILES and 'password' in request.POST:
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=email, password=password)
        if user is not None and user.is_staff:
            auth_login(request, user)
            return redirect('doctor-bulk-photo-tool')
        return render(request, 'doctors/bulk_photo_tool.html', {
            'login_error': 'Неверный email/пароль, либо у аккаунта нет прав администратора',
        })

    if not (request.user.is_authenticated and request.user.is_staff):
        return render(request, 'doctors/bulk_photo_tool.html', {})

    result = None
    if request.method == 'POST' and request.FILES.getlist('photos'):
        result = _match_and_apply_photos(request.FILES.getlist('photos'))

    return render(request, 'doctors/bulk_photo_tool.html', {'result': result})
