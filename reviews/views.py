from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count
from rest_framework import status, permissions
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardPagination
from .models import Review
from .serializers import ReviewSerializer, ReviewCreateSerializer


class IsAuthor(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.author == request.user


class IsReviewTarget(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.target_type == Review.TargetType.DOCTOR:
            return obj.doctor and obj.doctor.user == request.user
        elif obj.target_type == Review.TargetType.CLINIC:
            return obj.clinic and obj.clinic.user == request.user
        return False


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


class ReviewDetailView(RetrieveUpdateDestroyAPIView):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAuthenticated(), IsAuthor()]
        return [AllowAny()]

    def perform_destroy(self, instance):
        doctor = instance.doctor
        clinic = instance.clinic
        target_type = instance.target_type

        instance.delete()

        # Update rating/reviews count of doctor or clinic after deletion
        if target_type == Review.TargetType.DOCTOR and doctor:
            agg = Review.objects.filter(doctor=doctor).aggregate(avg=Avg('rating'), cnt=Count('id'))
            doctor.rating = round(agg['avg'] or 0, 2)
            doctor.reviews_count = agg['cnt']
            doctor.save(update_fields=['rating', 'reviews_count'])
        elif target_type == Review.TargetType.CLINIC and clinic:
            agg = Review.objects.filter(clinic=clinic).aggregate(avg=Avg('rating'), cnt=Count('id'))
            clinic.rating = round(agg['avg'] or 0, 2)
            clinic.reviews_count = agg['cnt']
            clinic.save(update_fields=['rating', 'reviews_count'])


class ReviewReplyView(APIView):
    permission_classes = [IsAuthenticated, IsReviewTarget]

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        self.check_object_permissions(request, review)

        text = request.data.get('text', '').strip()
        if not text:
            return Response({'text': 'Поле text обязательно.'}, status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone
        review.reply_text = text
        review.reply_created_at = timezone.now()
        review.save(update_fields=['reply_text', 'reply_created_at'])

        return Response(
            ReviewSerializer(review, context={'request': request}).data,
            status=status.HTTP_200_OK
        )

