from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import DestroyAPIView, ListAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments.models import Appointment
from core.pagination import StandardPagination
from reviews.models import Review
from users.models import Favorite, PatientProfile
from .serializers import (
    FavoriteCreateSerializer,
    FavoriteSerializer,
    PatientAppointmentSerializer,
    PatientProfileSerializer,
    PatientReviewSerializer,
)


class PatientProfileView(RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PatientProfileSerializer
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
    get=extend_schema(responses={200: FavoriteSerializer(many=True)}, tags=['Profile']),
    post=extend_schema(request=FavoriteCreateSerializer, responses={201: FavoriteSerializer}, tags=['Profile']),
)
class FavoriteListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        favorites = Favorite.objects.filter(user=request.user)
        serializer = FavoriteSerializer(favorites, many=True, context={'request': request})
        return Response({'data': serializer.data})

    def post(self, request):
        serializer = FavoriteCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        favorite = serializer.save()
        return Response(
            FavoriteSerializer(favorite, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(responses={204: None}, tags=['Profile'])
class FavoriteDeleteView(DestroyAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = FavoriteSerializer

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response(status=status.HTTP_204_NO_CONTENT)
