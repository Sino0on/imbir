from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from users.models import ClinicProfile
from core.pagination import StandardPagination
from .serializers import ClinicListSerializer, ClinicDetailSerializer


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
        if not city and hasattr(self.request, 'city'):
            city = self.request.city
        if city:
            qs = qs.filter(city__icontains=city)

        specialization = params.get('specialization', '').strip()
        if specialization:
            # JSONField-запросы к спискам несовместимы между SQLite и Postgres
            # (native jsonb vs текст с \uXXXX), поэтому фильтруем по элементам в Python.
            target = specialization.casefold()
            matched_ids = [
                pk
                for pk, primary, narrow in qs.values_list(
                    'pk', 'primary_specializations', 'narrow_specializations'
                )
                if any(
                    target == str(s).casefold()
                    for s in (primary or []) + (narrow or [])
                )
            ]
            qs = qs.filter(pk__in=matched_ids)

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

        has_joined_services = False
        min_price = params.get('min_price')
        if min_price:
            try:
                qs = qs.filter(services__price__gte=float(min_price))
                has_joined_services = True
            except ValueError:
                pass

        max_price = params.get('max_price')
        if max_price:
            try:
                qs = qs.filter(services__price__lte=float(max_price))
                has_joined_services = True
            except ValueError:
                pass

        if has_joined_services:
            qs = qs.distinct()

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
