from rest_framework import status
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.pagination import StandardPagination
from .models import Review
from .serializers import ReviewSerializer, ReviewCreateSerializer


class ReviewListCreateView(ListCreateAPIView):
    pagination_class = StandardPagination

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_queryset(self):
        qs = Review.objects.select_related('author')
        params = self.request.query_params

        target_type = params.get('target_type', '').strip()
        if target_type:
            qs = qs.filter(target_type=target_type)

        target_id = params.get('target_id', '').strip()
        if target_id:
            try:
                tid = int(target_id)
                if target_type == Review.TargetType.DOCTOR:
                    qs = qs.filter(doctor__user_id=tid)
                elif target_type == Review.TargetType.CLINIC:
                    qs = qs.filter(clinic__user_id=tid)
            except ValueError:
                pass

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        return Response(
            ReviewSerializer(review, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )
