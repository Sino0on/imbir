import json
from django.db.models import Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from users.models import ClinicProfile
from core.pagination import StandardPagination
from .serializers import ClinicListSerializer, ClinicDetailSerializer


def _json_escape(value: str) -> str:
    # SQLite JSONField stores Cyrillic as unicode-escape sequences
    return json.dumps(value, ensure_ascii=True)[1:-1]


class ClinicListView(ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ClinicListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = (
            ClinicProfile.objects
            .filter(user__is_active=True, is_published=True)
            .select_related('user')
            .order_by('-rating', '-reviews_count')
        )

        params = self.request.query_params

        search = params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)

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

        min_rating = params.get('min_rating')
        if min_rating:
            try:
                qs = qs.filter(rating__gte=float(min_rating))
            except ValueError:
                pass

        return qs


class ClinicDetailView(RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ClinicDetailSerializer

    def get_object(self):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(
            ClinicProfile.objects
            .select_related('user')
            .prefetch_related('photos')
            .filter(user__is_active=True, is_published=True),
            user__id=self.kwargs['pk'],
        )
