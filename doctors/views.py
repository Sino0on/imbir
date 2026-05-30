import json
from django.db.models import Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from users.models import DoctorProfile
from core.pagination import StandardPagination
from .serializers import DoctorListSerializer, DoctorDetailSerializer


def _json_escape(value: str) -> str:
    # SQLite JSONField хранит кириллицу как unicode-escape, нужна конвертация перед icontains
    return json.dumps(value, ensure_ascii=True)[1:-1]


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
