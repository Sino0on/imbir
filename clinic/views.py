import os
import uuid
from django.db.models import Count, Q, Sum
from django.core.files.storage import default_storage
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
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
from users.models import ClinicBranch, ClinicDocument, ClinicInvite, ClinicPhoto, ClinicProfile, DoctorClinicLink
from .permissions import IsClinic
from .serializers import (
    ClinicAppointmentSerializer,
    ClinicBranchUpdateSerializer,
    ClinicDoctorSerializer,
    ClinicInviteCreateSerializer,
    ClinicInviteSerializer,
    ClinicOwnProfileSerializer,
    ClinicReviewSerializer,
    ClinicServiceReadSerializer,
    ClinicServiceWriteSerializer,
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
        if status_filter:
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

@extend_schema(tags=['Clinic Cabinet'])
class ClinicDoctorListView(ListCreateAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicDoctorSerializer
    pagination_class = StandardPagination
    http_method_names = ['get']

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        return DoctorClinicLink.objects.filter(clinic=clinic).select_related('doctor__user')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['clinic'] = ClinicProfile.objects.get(user=self.request.user)
        return ctx


@extend_schema(responses={204: None}, tags=['Clinic Cabinet'])
class ClinicDoctorUnlinkView(DestroyAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicDoctorSerializer

    def get_queryset(self):
        clinic = ClinicProfile.objects.get(user=self.request.user)
        return DoctorClinicLink.objects.filter(clinic=clinic)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
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
        return Response(ClinicServiceReadSerializer(service).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    put=extend_schema(request=ClinicServiceWriteSerializer, responses={200: ClinicServiceReadSerializer}, tags=['Clinic Cabinet']),
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

    def put(self, request, pk):
        service = self._get_service(request, pk)
        if not service:
            return Response({'detail': 'Не найдено'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ClinicServiceWriteSerializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        return Response(ClinicServiceReadSerializer(service).data)

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
