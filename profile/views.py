from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import DestroyAPIView, ListAPIView, RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments.models import Appointment
from core.pagination import StandardPagination
from reviews.models import Review
from django.shortcuts import get_object_or_404
from users.models import PatientProfile, User, DoctorProfile, ClinicProfile
from services.models import Service
from .serializers import (
    FavoritesListSerializer,
    FavoriteActionSerializer,
    PatientAppointmentSerializer,
    PatientProfileSerializer,
    PatientReviewSerializer,
)


class PatientProfileView(RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PatientProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    http_method_names = ['get', 'put']

    def get_object(self):
        profile, _ = PatientProfile.objects.select_related('user').get_or_create(
            user=self.request.user,
        )
        return profile


class PatientAppointmentListView(ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PatientAppointmentSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = (
            Appointment.objects
            .filter(patient=self.request.user)
            .select_related('doctor__user', 'clinic', 'service', 'review')
            .order_by('-date', '-time')
        )

        status_filter = self.request.query_params.get('status', '').strip()
        if status_filter == 'upcoming':
            qs = qs.filter(status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED])
        elif status_filter == 'completed':
            qs = qs.filter(status=Appointment.Status.COMPLETED)
        elif status_filter == 'cancelled':
            qs = qs.filter(status=Appointment.Status.CANCELLED)

        return qs


class PatientReviewListView(ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PatientReviewSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            Review.objects
            .filter(author=self.request.user)
            .select_related('doctor__user', 'clinic')
            .order_by('-created_at')
        )


@extend_schema_view(
    get=extend_schema(responses={200: FavoritesListSerializer}, tags=['Profile'], summary='Получить список избранного'),
    post=extend_schema(request=FavoriteActionSerializer, responses={201: FavoritesListSerializer}, tags=['Profile'], summary='Добавить врача, клинику или услугу в избранное'),
    delete=extend_schema(
        parameters=[],
        request=FavoriteActionSerializer,
        responses={204: None},
        tags=['Profile'],
        summary='Удалить врача, клинику или услугу из избранного'
    ),
)
class FavoriteListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        user_with_favorites = (
            User.objects.prefetch_related(
                'favorite_doctors__user',
                'favorite_clinics',
                'favorite_services'
            )
            .get(id=user.id)
        )
        serializer = FavoritesListSerializer(user_with_favorites, context={'request': request})
        return Response({'data': serializer.data})

    def post(self, request):
        serializer = FavoriteActionSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        target_type = serializer.validated_data['target_type']
        target_id = serializer.validated_data['target_id']
        user = request.user

        if target_type == 'doctor':
            doctor = DoctorProfile.objects.get(user_id=target_id)
            user.favorite_doctors.add(doctor)
        elif target_type == 'clinic':
            clinic = ClinicProfile.objects.get(user_id=target_id)
            user.favorite_clinics.add(clinic)
        elif target_type == 'service':
            service = Service.objects.get(id=target_id)
            user.favorite_services.add(service)

        full_serializer = FavoritesListSerializer(user, context={'request': request})
        return Response(full_serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        target_type = request.query_params.get('target_type') or request.data.get('target_type')
        target_id = request.query_params.get('target_id') or request.data.get('target_id')

        if not target_type or not target_id:
            return Response(
                {'detail': 'Параметры target_type и target_id обязательны.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            target_id = int(target_id)
        except ValueError:
            return Response(
                {'detail': 'Некорректный target_id.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        if target_type == 'doctor':
            doctor = get_object_or_404(DoctorProfile, user_id=target_id)
            user.favorite_doctors.remove(doctor)
        elif target_type == 'clinic':
            clinic = get_object_or_404(ClinicProfile, user_id=target_id)
            user.favorite_clinics.remove(clinic)
        elif target_type == 'service':
            service = get_object_or_404(Service, id=target_id)
            user.favorite_services.remove(service)
        else:
            return Response(
                {'detail': 'Некорректный target_type.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
