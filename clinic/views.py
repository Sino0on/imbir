import os
import uuid
from django.db.models import Count, Q, Sum
from django.core.files.storage import default_storage
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.generics import DestroyAPIView, ListCreateAPIView, RetrieveUpdateAPIView, UpdateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments.models import Appointment
from core.pagination import StandardPagination
from reviews.models import Review
from services.models import Service
from users.models import (
    ClinicBranch, ClinicDocument, ClinicInvite, ClinicPhoto, ClinicProfile, DoctorClinicLink,
    DoctorDocument, DoctorInvitation, DoctorProfile,
)
from .permissions import IsClinic
from .serializers import (
    ClinicAppointmentSerializer,
    ClinicBranchUpdateSerializer,
    ClinicDoctorSerializer,
    ClinicDoctorProfileSerializer,
    ClinicInviteCreateSerializer,
    ClinicInviteSerializer,
    ClinicOwnProfileSerializer,
    ClinicReviewSerializer,
    ClinicServiceReadSerializer,
    ClinicServiceWriteSerializer,
    ClinicDoctorCreateSerializer,
    DoctorInvitationClinicSerializer,
    DoctorInvitationCreateSerializer,
)


# ── Profile ─────────────────────────────────────────────────────────────────

@extend_schema(tags=['Clinic Cabinet'])
class ClinicProfileView(RetrieveUpdateAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicOwnProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    http_method_names = ['get', 'put']

    def get_object(self):
        return ClinicProfile.objects.prefetch_related('branches').get(user=self.request.user)


# ── Branches ─────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(responses={200: ClinicBranchUpdateSerializer(many=True)}, tags=['Clinic Cabinet'], summary='Список филиалов клиники'),
    post=extend_schema(request=ClinicBranchUpdateSerializer, responses={201: ClinicBranchUpdateSerializer}, tags=['Clinic Cabinet'], summary='Добавить филиал'),
)
class BranchListCreateView(ListCreateAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicBranchUpdateSerializer

    def get_queryset(self):
        return ClinicBranch.objects.filter(clinic__user=self.request.user).order_by('id')

    def perform_create(self, serializer):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        serializer.save(clinic=clinic)


@extend_schema(tags=['Clinic Cabinet'])
class BranchUpdateView(UpdateAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicBranchUpdateSerializer
    http_method_names = ['put']

    def get_queryset(self):
        return ClinicBranch.objects.filter(clinic__user=self.request.user)


# ── Appointments ─────────────────────────────────────────────────────────────

@extend_schema(tags=['Clinic Cabinet'])
class ClinicAppointmentListView(ListCreateAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicAppointmentSerializer
    pagination_class = StandardPagination
    http_method_names = ['get']

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        qs = (
            Appointment.objects
            .filter(clinic=clinic)
            .select_related('patient', 'doctor__user', 'service')
            .order_by('-date', '-time')
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

        doctor_id = params.get('doctor_id', '').strip()
        if doctor_id:
            qs = qs.filter(doctor__user_id=doctor_id)

        date_from = params.get('date_from', '').strip()
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = params.get('date_to', '').strip()
        if date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


# ── Stats ─────────────────────────────────────────────────────────────────────

@extend_schema(
    responses={200: inline_serializer('ClinicStats', fields={
        'profile_views': serializers.IntegerField(),
        'profile_views_this_month': serializers.IntegerField(),
        'appointments_total': serializers.IntegerField(),
        'appointments_this_month': serializers.IntegerField(),
        'average_rating': serializers.FloatField(),
        'reviews_count': serializers.IntegerField(),
        'doctors_count': serializers.IntegerField(),
        'patients_total': serializers.IntegerField(),
        'revenue_this_month': serializers.FloatField(),
    })},
    tags=['Clinic Cabinet'],
)
class ClinicStatsView(APIView):
    permission_classes = (IsClinic,)

    def get(self, request):
        clinic = ClinicProfile.objects.get(user=request.user)
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        appts = Appointment.objects.filter(clinic=clinic)
        appts_month = appts.filter(created_at__gte=month_start)

        agg = appts_month.aggregate(
            revenue=Sum('service__price', filter=Q(status=Appointment.Status.COMPLETED)),
        )

        return Response({
            'profile_views': clinic.profile_views,
            'profile_views_this_month': 0,
            'appointments_total': appts.count(),
            'appointments_this_month': appts_month.count(),
            'average_rating': float(clinic.rating),
            'reviews_count': clinic.reviews_count,
            'doctors_count': DoctorClinicLink.objects.filter(clinic=clinic, is_active=True).count(),
            'patients_total': appts.filter(patient__isnull=False).values('patient').distinct().count(),
            'revenue_this_month': float(agg['revenue'] or 0),
        })


# ── Reviews ──────────────────────────────────────────────────────────────────

@extend_schema(tags=['Clinic Cabinet'])
class ClinicReviewListView(ListCreateAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicReviewSerializer
    pagination_class = StandardPagination
    http_method_names = ['get']

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        return Review.objects.filter(clinic=clinic).select_related('author').order_by('-created_at')


# ── Doctors ──────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(responses={200: ClinicDoctorSerializer(many=True)}, tags=['Clinic Cabinet'], summary='Список врачей клиники'),
    post=extend_schema(request=ClinicDoctorCreateSerializer, responses={201: ClinicDoctorSerializer}, tags=['Clinic Cabinet'], summary='Создать и привязать врача'),
)
class ClinicDoctorListView(ListCreateAPIView):
    permission_classes = (IsClinic,)
    pagination_class = StandardPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ClinicDoctorCreateSerializer
        return ClinicDoctorSerializer

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        return DoctorClinicLink.objects.filter(clinic=clinic).select_related('doctor__user')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['clinic'] = ClinicProfile.objects.get(user=self.request.user)
        return ctx

    def post(self, request, *args, **kwargs):
        serializer = ClinicDoctorCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        link = serializer.save()
        return Response(ClinicDoctorSerializer(link, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(responses={200: ClinicDoctorProfileSerializer}, tags=['Clinic Cabinet'],
                       summary='Карточка прикреплённого врача'),
    patch=extend_schema(request=ClinicDoctorProfileSerializer, responses={200: ClinicDoctorProfileSerializer},
                         tags=['Clinic Cabinet'], summary='Править данные прикреплённого врача'),
    delete=extend_schema(responses={204: None}, tags=['Clinic Cabinet'], summary='Открепить врача от клиники'),
)
class ClinicDoctorDetailView(RetrieveUpdateAPIView):
    """Уже прикреплённый к клинике врач: GET/PATCH — карточка и правка полей, которые
    заполняет клиника при найме; DELETE — открепление от клиники (сам аккаунт врача
    не удаляется). Найти можно только среди врачей, реально привязанных к этой клинике."""
    permission_classes = (IsClinic,)
    serializer_class = ClinicDoctorProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    http_method_names = ['get', 'patch', 'delete']
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        return DoctorProfile.objects.filter(
            clinic_links__clinic=clinic, clinic_links__is_active=True,
        ).select_related('user').distinct()

    def get_object(self):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(self.get_queryset(), user_id=self.kwargs['pk'])

    def delete(self, request, *args, **kwargs):
        doctor = self.get_object()
        clinic = ClinicProfile.objects.get(user=request.user)
        DoctorClinicLink.objects.filter(clinic=clinic, doctor=doctor).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(tags=['Clinic Cabinet'], summary='Документы (сертификаты) прикреплённого врача'),
    post=extend_schema(tags=['Clinic Cabinet'], summary='Загрузить документ прикреплённому врачу'),
)
class ClinicDoctorDocumentListCreateView(APIView):
    permission_classes = (IsClinic,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def _get_doctor(self, request, pk):
        clinic = ClinicProfile.objects.get(user=request.user)
        from django.shortcuts import get_object_or_404
        return get_object_or_404(
            DoctorProfile.objects.filter(clinic_links__clinic=clinic, clinic_links__is_active=True).distinct(),
            user_id=pk,
        )

    def get(self, request, pk):
        doctor = self._get_doctor(request, pk)
        docs = doctor.documents.all().order_by('uploaded_at')
        data = [{
            'id': d.id,
            'url': request.build_absolute_uri(d.file.url),
            'uploaded_at': d.uploaded_at,
        } for d in docs]
        return Response(data)

    def post(self, request, pk):
        doctor = self._get_doctor(request, pk)

        uploaded_file = request.FILES.get('file')
        url_str = (request.data.get('url') or '').strip()

        if uploaded_file:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            filename = f'doctors/documents/{uuid.uuid4().hex}{ext}'
            saved_path = default_storage.save(filename, uploaded_file)
            doc = DoctorDocument.objects.create(doctor=doctor, file=saved_path)
        elif url_str:
            from users.utils import get_relative_path_from_url
            rel_path = get_relative_path_from_url(url_str)
            doc = DoctorDocument.objects.create(doctor=doctor, file=rel_path)
        else:
            return Response({'detail': 'Необходимо передать file (multipart) или url (строка).'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': doc.id,
            'url': request.build_absolute_uri(doc.file.url),
            'uploaded_at': doc.uploaded_at,
        }, status=status.HTTP_201_CREATED)


@extend_schema(responses={204: None}, tags=['Clinic Cabinet'], summary='Удалить документ прикреплённого врача')
class ClinicDoctorDocumentDeleteView(APIView):
    permission_classes = (IsClinic,)

    def delete(self, request, pk, doc_id):
        clinic = ClinicProfile.objects.get(user=request.user)
        from django.shortcuts import get_object_or_404
        doctor = get_object_or_404(
            DoctorProfile.objects.filter(clinic_links__clinic=clinic, clinic_links__is_active=True).distinct(),
            user_id=pk,
        )
        doc = get_object_or_404(DoctorDocument, pk=doc_id, doctor=doctor)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Services ─────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(responses={200: ClinicServiceReadSerializer(many=True)}, tags=['Clinic Cabinet']),
    post=extend_schema(request=ClinicServiceWriteSerializer, responses={201: ClinicServiceReadSerializer}, tags=['Clinic Cabinet']),
)
class ClinicServiceListCreateView(ListCreateAPIView):
    permission_classes = (IsClinic,)
    pagination_class = StandardPagination

    def get_serializer_class(self):
        return ClinicServiceWriteSerializer if self.request.method == 'POST' else ClinicServiceReadSerializer

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        return Service.objects.filter(clinic=clinic).order_by('category', 'name')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['clinic'] = ClinicProfile.objects.get(user=self.request.user)
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        return Response(ClinicServiceReadSerializer(service, context={'request': request}).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(responses={200: ClinicServiceReadSerializer}, tags=['Clinic Cabinet'], summary='Карточка процедуры'),
    put=extend_schema(request=ClinicServiceWriteSerializer, responses={200: ClinicServiceReadSerializer}, tags=['Clinic Cabinet']),
    patch=extend_schema(request=ClinicServiceWriteSerializer, responses={200: ClinicServiceReadSerializer}, tags=['Clinic Cabinet']),
    delete=extend_schema(responses={204: None}, tags=['Clinic Cabinet']),
)
class ClinicServiceDetailView(APIView):
    permission_classes = (IsClinic,)

    def _get_service(self, request, pk):
        clinic = ClinicProfile.objects.get(user=request.user)
        try:
            return Service.objects.get(pk=pk, clinic=clinic)
        except Service.DoesNotExist:
            return None

    def get(self, request, pk):
        service = self._get_service(request, pk)
        if not service:
            return Response({'detail': 'Не найдено'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ClinicServiceReadSerializer(service, context={'request': request}).data)

    def put(self, request, pk):
        service = self._get_service(request, pk)
        if not service:
            return Response({'detail': 'Не найдено'}, status=status.HTTP_404_NOT_FOUND)
        clinic = ClinicProfile.objects.get(user=request.user)
        serializer = ClinicServiceWriteSerializer(
            service,
            data=request.data,
            partial=True,
            context={'clinic': clinic, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        service.refresh_from_db()
        return Response(ClinicServiceReadSerializer(service, context={'request': request}).data)

    # put уже реализован как частичное обновление (partial=True) — просто даём
    # вызывать его и через PATCH, раз по факту это он и есть.
    patch = put

    def delete(self, request, pk):
        service = self._get_service(request, pk)
        if not service:
            return Response({'detail': 'Не найдено'}, status=status.HTTP_404_NOT_FOUND)
        service.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Invites ──────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(responses={200: ClinicInviteSerializer(many=True)}, tags=['Clinic Cabinet']),
    post=extend_schema(request=ClinicInviteCreateSerializer, responses={201: ClinicInviteSerializer}, tags=['Clinic Cabinet']),
)
class InviteListCreateView(ListCreateAPIView):
    permission_classes = (IsClinic,)

    def get_serializer_class(self):
        return ClinicInviteCreateSerializer if self.request.method == 'POST' else ClinicInviteSerializer

    def get_queryset(self):
        return ClinicInvite.objects.filter(clinic__user=self.request.user).select_related('branch').order_by('-created_at')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['clinic'] = self.request.user.clinic_profile
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.save()
        return Response(ClinicInviteSerializer(invite).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={204: None}, tags=['Clinic Cabinet'])
class InviteDeleteView(DestroyAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicInviteSerializer

    def get_queryset(self):
        return ClinicInvite.objects.filter(clinic__user=self.request.user)


# ── Doctor invitations (прицельные, не обезличенные ссылки) ──────────────────

@extend_schema_view(
    get=extend_schema(
        parameters=[OpenApiParameter(
            name='status', type=str, required=False,
            description='Фильтр: pending / accepted / declined',
        )],
        responses={200: DoctorInvitationClinicSerializer(many=True)}, tags=['Clinic Cabinet'],
        summary='Список приглашений, отправленных врачам',
    ),
    post=extend_schema(
        request=DoctorInvitationCreateSerializer, responses={201: DoctorInvitationClinicSerializer},
        tags=['Clinic Cabinet'], summary='Пригласить врача в клинику',
    ),
)
class DoctorInvitationListCreateView(ListCreateAPIView):
    permission_classes = (IsClinic,)
    pagination_class = StandardPagination

    def get_serializer_class(self):
        return DoctorInvitationCreateSerializer if self.request.method == 'POST' else DoctorInvitationClinicSerializer

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        qs = (
            DoctorInvitation.objects.filter(clinic=clinic)
            .select_related('doctor__user', 'branch')
        )
        status_filter = self.request.query_params.get('status', '').strip()
        if status_filter in dict(DoctorInvitation.Status.choices):
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['clinic'] = ClinicProfile.objects.get(user=self.request.user)
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = serializer.save()
        self._notify_doctor(invitation)
        return Response(
            DoctorInvitationClinicSerializer(invitation, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def _notify_doctor(self, invitation):
        from notifications.models import Notification
        from notifications.utils import notify

        notify(
            invitation.doctor.user, Notification.Type.CLINIC_INVITE_RECEIVED,
            'Приглашение от клиники',
            f'{invitation.clinic.name} приглашает вас присоединиться.',
            {'invitation_id': invitation.id, 'clinic_id': invitation.clinic.user_id},
        )


@extend_schema(
    responses={204: None}, tags=['Clinic Cabinet'],
    summary='Отменить приглашение (только пока врач не ответил)',
)
class DoctorInvitationDeleteView(DestroyAPIView):
    permission_classes = (IsClinic,)
    serializer_class = DoctorInvitationClinicSerializer

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        return DoctorInvitation.objects.filter(clinic=clinic, status=DoctorInvitation.Status.PENDING)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _save_file_or_url(request, folder, model_class, profile, field_name='file'):
    """Helper: сохраняет multipart-файл или URL и создаёт запись в модель."""
    from users.utils import get_relative_path_from_url
    uploaded_file = request.FILES.get('file')
    url_str = request.data.get('url', '').strip()

    if uploaded_file:
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        filename = f'{folder}/{uuid.uuid4().hex}{ext}'
        saved_path = default_storage.save(filename, uploaded_file)
        return model_class.objects.create(**{field_name: saved_path, 'clinic': profile})
    elif url_str:
        rel_path = get_relative_path_from_url(url_str)
        return model_class.objects.create(**{field_name: rel_path, 'clinic': profile})
    return None


# ── Clinic Photos ────────────────────────────────────────────────────────────

@extend_schema(
    request=inline_serializer('ClinicPhotoUpload', fields={
        'file': serializers.FileField(required=False),
        'url': serializers.CharField(required=False),
    }),
    responses={201: inline_serializer('ClinicPhotoOut', fields={
        'id': serializers.IntegerField(),
        'url': serializers.CharField(),
        'uploaded_at': serializers.DateTimeField(),
    })},
    tags=['Clinic Cabinet'],
    summary='Список и загрузка фотогалереи клиники',
)
class ClinicPhotoListCreateView(APIView):
    permission_classes = (IsClinic,)
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        clinic = ClinicProfile.objects.get(user=request.user)
        data = [{
            'id': p.id,
            'url': request.build_absolute_uri(p.image.url),
            'uploaded_at': p.uploaded_at,
        } for p in clinic.photos.all().order_by('uploaded_at')]
        return Response(data)

    def post(self, request):
        clinic = ClinicProfile.objects.get(user=request.user)
        uploaded_file = request.FILES.get('file')
        url_str = request.data.get('url', '').strip()

        if uploaded_file:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            filename = f'clinics/photos/{uuid.uuid4().hex}{ext}'
            saved_path = default_storage.save(filename, uploaded_file)
            photo = ClinicPhoto.objects.create(clinic=clinic, image=saved_path)
        elif url_str:
            from users.utils import get_relative_path_from_url
            photo = ClinicPhoto.objects.create(clinic=clinic, image=get_relative_path_from_url(url_str))
        else:
            return Response({'detail': 'Необходимо передать file или url.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': photo.id,
            'url': request.build_absolute_uri(photo.image.url),
            'uploaded_at': photo.uploaded_at,
        }, status=status.HTTP_201_CREATED)


@extend_schema(responses={204: None}, tags=['Clinic Cabinet'], summary='Удалить фото клиники')
class ClinicPhotoDeleteView(APIView):
    permission_classes = (IsClinic,)

    def delete(self, request, pk):
        from django.shortcuts import get_object_or_404
        clinic = ClinicProfile.objects.get(user=request.user)
        photo = get_object_or_404(ClinicPhoto, pk=pk, clinic=clinic)
        photo.image.delete(save=False)
        photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Clinic Documents ─────────────────────────────────────────────────────────

@extend_schema(
    request=inline_serializer('ClinicDocumentUpload', fields={
        'file': serializers.FileField(required=False),
        'url': serializers.CharField(required=False),
    }),
    responses={201: inline_serializer('ClinicDocumentOut', fields={
        'id': serializers.IntegerField(),
        'url': serializers.CharField(),
        'uploaded_at': serializers.DateTimeField(),
    })},
    tags=['Clinic Cabinet'],
    summary='Список и загрузка документов клиники',
)
class ClinicDocumentListCreateView(APIView):
    permission_classes = (IsClinic,)
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        clinic = ClinicProfile.objects.get(user=request.user)
        data = [{
            'id': d.id,
            'url': request.build_absolute_uri(d.file.url),
            'uploaded_at': d.uploaded_at,
        } for d in clinic.documents.all().order_by('uploaded_at')]
        return Response(data)

    def post(self, request):
        clinic = ClinicProfile.objects.get(user=request.user)
        uploaded_file = request.FILES.get('file')
        url_str = request.data.get('url', '').strip()

        if uploaded_file:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            filename = f'clinics/documents/{uuid.uuid4().hex}{ext}'
            saved_path = default_storage.save(filename, uploaded_file)
            doc = ClinicDocument.objects.create(clinic=clinic, file=saved_path)
        elif url_str:
            from users.utils import get_relative_path_from_url
            doc = ClinicDocument.objects.create(clinic=clinic, file=get_relative_path_from_url(url_str))
        else:
            return Response({'detail': 'Необходимо передать file или url.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': doc.id,
            'url': request.build_absolute_uri(doc.file.url),
            'uploaded_at': doc.uploaded_at,
        }, status=status.HTTP_201_CREATED)


@extend_schema(responses={204: None}, tags=['Clinic Cabinet'], summary='Удалить документ клиники')
class ClinicDocumentDeleteView(APIView):
    permission_classes = (IsClinic,)

    def delete(self, request, pk):
        from django.shortcuts import get_object_or_404
        clinic = ClinicProfile.objects.get(user=request.user)
        doc = get_object_or_404(ClinicDocument, pk=pk, clinic=clinic)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
