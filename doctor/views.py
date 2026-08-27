import os
import uuid
from django.shortcuts import get_object_or_404
from django.db.models import Count, Max, Q
from django.core.files.storage import default_storage
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments.models import Appointment
from core.pagination import StandardPagination
from reviews.models import Review
from services.models import Service
from users.models import DoctorDocument, DoctorProfile, User
from doctors.models import Interview
from .permissions import IsDoctor
from .serializers import (
    DoctorAppointmentSerializer,
    DoctorOwnProfileSerializer,
    DoctorPatientSerializer,
    DoctorReviewSerializer,
    DoctorScheduleSerializer,
    DoctorServiceReadSerializer,
    DoctorServiceWriteSerializer,
    DoctorAppointmentSummarySerializer,
    DoctorInterviewSerializer,
)


@extend_schema_view(
    put=extend_schema(
        parameters=[
            OpenApiParameter(
                name='process_photo', type=bool, required=False,
                description=(
                    'Если true и в этом же запросе передано новое фото (поле photo, файл) — '
                    'оно будет обработано через ИИ: на человека наденут белый медицинский халат '
                    'и поместят на белый фон. При неудаче обработки сохраняется исходное фото '
                    'как есть, и в ответе появляется "photo_ai_processing": "failed". Если '
                    'функция выключена в настройках сайта (админка) — "photo_ai_processing": '
                    '"disabled", фото тоже сохраняется как есть.'
                ),
            ),
        ],
        tags=['Doctor Cabinet'],
    ),
)
class DoctorProfileView(RetrieveUpdateAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorOwnProfileSerializer
    http_method_names = ['get', 'put']

    def get_object(self):
        return DoctorProfile.objects.select_related('user').get(user=self.request.user)

    def update(self, request, *args, **kwargs):
        from references.models import SiteSettings

        should_process = request.query_params.get('process_photo', '').strip().lower() in ('1', 'true', 'yes')
        ai_enabled = SiteSettings.load().ai_doctor_photo_processing_enabled
        uploaded_photo = request.FILES.get('photo')
        photo_bytes = None
        if should_process and uploaded_photo and ai_enabled:
            photo_bytes = uploaded_photo.read()
            uploaded_photo.seek(0)  # чтобы обычное сохранение через сериализатор тоже отработало штатно

        response = super().update(request, *args, **kwargs)

        if should_process and uploaded_photo and not ai_enabled and response.status_code == 200:
            response.data['photo_ai_processing'] = 'disabled'

        if photo_bytes and response.status_code == 200:
            from .ai_photo import generate_doctor_coat_photo
            processed = generate_doctor_coat_photo(photo_bytes, uploaded_photo.name)
            if processed:
                from django.core.files.base import ContentFile
                profile = self.get_object()
                profile.photo.save(f'{profile.user_id}_coat.png', ContentFile(processed), save=True)
                response = Response(self.get_serializer(profile).data)
            else:
                response.data['photo_ai_processing'] = 'failed'
        return response


class DoctorScheduleView(RetrieveUpdateAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorScheduleSerializer
    http_method_names = ['get', 'put']

    def get_object(self):
        return DoctorProfile.objects.get(user=self.request.user)


class DoctorAppointmentListView(ListAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorAppointmentSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        doctor_profile = DoctorProfile.objects.get(user=self.request.user)
        qs = (
            Appointment.objects
            .filter(doctor=doctor_profile)
            .select_related('patient', 'service')
            .order_by('date', 'time')
        )

        params = self.request.query_params

        status_filter = params.get('status', '').strip()
        if status_filter == 'upcoming':
            qs = qs.filter(status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED])
        elif status_filter == 'completed':
            qs = qs.filter(status=Appointment.Status.COMPLETED)
        elif status_filter == 'cancelled':
            qs = qs.filter(status=Appointment.Status.CANCELLED)
        elif status_filter:
            qs = qs.filter(status=status_filter)

        date_filter = params.get('date', '').strip()
        if date_filter:
            qs = qs.filter(date=date_filter)

        date_from = params.get('date_from', '').strip()
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = params.get('date_to', '').strip()
        if date_to:
            qs = qs.filter(date__lte=date_to)

        is_online = params.get('is_online')
        if is_online is not None:
            qs = qs.filter(is_online=is_online.lower() in ('true', '1', 'yes'))

        return qs


class DoctorPatientListView(ListAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorPatientSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        doctor_profile = DoctorProfile.objects.get(user=self.request.user)
        doctor_filter = Q(appointments__doctor=doctor_profile)

        qs = (
            User.objects
            .filter(doctor_filter)
            .annotate(
                visits_count=Count('appointments', filter=doctor_filter),
                last_visit=Max('appointments__date', filter=doctor_filter),
            )
            .distinct()
            .order_by('-last_visit')
        )

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['doctor_profile'] = DoctorProfile.objects.get(user=self.request.user)
        return ctx


@extend_schema(
    responses={200: inline_serializer('DoctorStats', fields={
        'profile_views': serializers.IntegerField(),
        'rating': serializers.FloatField(),
        'reviews_count': serializers.IntegerField(),
        'appointments': inline_serializer('AppointmentCounts', fields={
            'total': serializers.IntegerField(),
            'pending': serializers.IntegerField(),
            'confirmed': serializers.IntegerField(),
            'completed': serializers.IntegerField(),
            'cancelled': serializers.IntegerField(),
        }),
        'patients_count': serializers.IntegerField(),
        'completion_rate': serializers.FloatField(),
    })},
    tags=['Doctor Cabinet'],
)
class DoctorStatsView(APIView):
    permission_classes = (IsDoctor,)

    def get(self, request):
        profile = DoctorProfile.objects.get(user=request.user)

        agg = Appointment.objects.filter(doctor=profile).aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status=Appointment.Status.PENDING)),
            confirmed=Count('id', filter=Q(status=Appointment.Status.CONFIRMED)),
            completed=Count('id', filter=Q(status=Appointment.Status.COMPLETED)),
            cancelled=Count('id', filter=Q(status=Appointment.Status.CANCELLED)),
            patients_count=Count('patient', distinct=True, filter=Q(patient__isnull=False)),
        )

        total = agg['total'] or 0
        completed = agg['completed'] or 0
        completion_rate = round(completed / total * 100, 1) if total else 0.0

        return Response({
            'profile_views': profile.profile_views,
            'rating': float(profile.rating),
            'reviews_count': profile.reviews_count,
            'appointments': {
                'total': total,
                'pending': agg['pending'],
                'confirmed': agg['confirmed'],
                'completed': completed,
                'cancelled': agg['cancelled'],
            },
            'patients_count': agg['patients_count'],
            'completion_rate': completion_rate,
        })


@extend_schema(tags=['Doctor Cabinet'])
class DoctorReviewListView(ListAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorReviewSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        profile = DoctorProfile.objects.get(user=self.request.user)
        return Review.objects.filter(doctor=profile).select_related('author').order_by('-created_at')


@extend_schema_view(
    get=extend_schema(responses={200: DoctorServiceReadSerializer(many=True)}, tags=['Doctor Cabinet']),
    post=extend_schema(request=DoctorServiceWriteSerializer, responses={201: DoctorServiceReadSerializer}, tags=['Doctor Cabinet']),
)
class DoctorServiceListCreateView(ListAPIView):
    permission_classes = (IsDoctor,)
    pagination_class = StandardPagination

    def get_serializer_class(self):
        return DoctorServiceWriteSerializer if self.request.method == 'POST' else DoctorServiceReadSerializer

    def get_queryset(self):
        profile = DoctorProfile.objects.get(user=self.request.user)
        return profile.services.all().order_by('category', 'name')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['doctor'] = DoctorProfile.objects.get(user=self.request.user)
        return ctx

    def post(self, request, *args, **kwargs):
        serializer = DoctorServiceWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        return Response(
            DoctorServiceReadSerializer(service, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    put=extend_schema(request=DoctorServiceWriteSerializer, responses={200: DoctorServiceReadSerializer}, tags=['Doctor Cabinet']),
    delete=extend_schema(responses={204: None}, tags=['Doctor Cabinet']),
)
class DoctorServiceDetailView(APIView):
    permission_classes = (IsDoctor,)

    def _get_service(self, request, pk):
        profile = DoctorProfile.objects.get(user=request.user)
        try:
            return profile.services.get(pk=pk)
        except Service.DoesNotExist:
            return None

    def put(self, request, pk):
        service = self._get_service(request, pk)
        if not service:
            return Response({'detail': 'Не найдено'}, status=status.HTTP_404_NOT_FOUND)
        serializer = DoctorServiceWriteSerializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        return Response(DoctorServiceReadSerializer(service, context={'request': request}).data)

    def delete(self, request, pk):
        service = self._get_service(request, pk)
        if not service:
            return Response({'detail': 'Не найдено'}, status=status.HTTP_404_NOT_FOUND)
        service.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(responses={200: DoctorAppointmentSummarySerializer}, tags=['Doctor Cabinet']),
    patch=extend_schema(request=DoctorAppointmentSummarySerializer, responses={200: DoctorAppointmentSummarySerializer}, tags=['Doctor Cabinet']),
)
class DoctorAppointmentSummaryView(RetrieveUpdateAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorAppointmentSummarySerializer
    http_method_names = ['get', 'patch']

    def get_object(self):
        doctor_profile = DoctorProfile.objects.get(user=self.request.user)
        return get_object_or_404(
            Appointment.objects.filter(doctor=doctor_profile),
            pk=self.kwargs['pk']
        )


@extend_schema(
    request=inline_serializer('DoctorDocumentUpload', fields={
        'file': serializers.FileField(required=False, help_text='Multipart-файл'),
        'url': serializers.CharField(required=False, help_text='URL из /api/upload/'),
    }),
    responses={201: inline_serializer('DoctorDocumentOut', fields={
        'id': serializers.IntegerField(),
        'url': serializers.CharField(),
        'uploaded_at': serializers.DateTimeField(),
    })},
    tags=['Doctor Cabinet'],
    summary='Список и загрузка документов/сертификатов врача',
)
class DoctorDocumentListCreateView(APIView):
    permission_classes = (IsDoctor,)
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        profile = DoctorProfile.objects.get(user=request.user)
        docs = profile.documents.all().order_by('uploaded_at')
        data = [{
            'id': d.id,
            'url': request.build_absolute_uri(d.file.url),
            'uploaded_at': d.uploaded_at,
        } for d in docs]
        return Response(data)

    def post(self, request):
        profile = DoctorProfile.objects.get(user=request.user)

        uploaded_file = request.FILES.get('file')
        url_str = request.data.get('url', '').strip()

        if uploaded_file:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            filename = f'doctors/documents/{uuid.uuid4().hex}{ext}'
            saved_path = default_storage.save(filename, uploaded_file)
            doc = DoctorDocument.objects.create(doctor=profile, file=saved_path)
        elif url_str:
            from users.utils import get_relative_path_from_url
            rel_path = get_relative_path_from_url(url_str)
            doc = DoctorDocument.objects.create(doctor=profile, file=rel_path)
        else:
            return Response({'detail': 'Необходимо передать file (multipart) или url (строка).'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': doc.id,
            'url': request.build_absolute_uri(doc.file.url),
            'uploaded_at': doc.uploaded_at,
        }, status=status.HTTP_201_CREATED)


@extend_schema(responses={204: None}, tags=['Doctor Cabinet'], summary='Удалить документ врача')
class DoctorDocumentDeleteView(APIView):
    permission_classes = (IsDoctor,)

    def delete(self, request, pk):
        profile = DoctorProfile.objects.get(user=request.user)
        doc = get_object_or_404(DoctorDocument, pk=pk, doctor=profile)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(responses={200: DoctorInterviewSerializer(many=True)}, tags=['Doctor Cabinet'], summary='Список видео-интервью врача'),
    post=extend_schema(request=DoctorInterviewSerializer, responses={201: DoctorInterviewSerializer}, tags=['Doctor Cabinet'], summary='Добавить новое видео-интервью врача'),
)
class DoctorInterviewListCreateView(ListCreateAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorInterviewSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        profile = DoctorProfile.objects.get(user=self.request.user)
        return Interview.objects.filter(doctor=profile).order_by('-priority', 'id')


@extend_schema_view(
    get=extend_schema(responses={200: DoctorInterviewSerializer}, tags=['Doctor Cabinet'], summary='Детали видео-интервью врача'),
    put=extend_schema(request=DoctorInterviewSerializer, responses={200: DoctorInterviewSerializer}, tags=['Doctor Cabinet'], summary='Редактировать видео-интервью врача (полностью)'),
    patch=extend_schema(request=DoctorInterviewSerializer, responses={200: DoctorInterviewSerializer}, tags=['Doctor Cabinet'], summary='Редактировать видео-интервью врача (частично)'),
    delete=extend_schema(responses={204: None}, tags=['Doctor Cabinet'], summary='Удалить видео-интервью врача'),
)
class DoctorInterviewDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = (IsDoctor,)
    serializer_class = DoctorInterviewSerializer

    def get_queryset(self):
        profile = DoctorProfile.objects.get(user=self.request.user)
        return Interview.objects.filter(doctor=profile)
