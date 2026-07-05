from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from core.pagination import StandardPagination
from .models import Service
from .serializers import ServiceListSerializer, ServiceDetailSerializer


class ServiceListView(ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ServiceListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = (
            Service.objects
            .filter(is_active=True)
            .select_related('clinic')
            .prefetch_related('doctors__user')
        )

        params = self.request.query_params

        category = params.get('category', '').strip()
        if category:
            qs = qs.filter(category__icontains=category)

        clinic_id = params.get('clinic_id')
        if clinic_id:
            try:
                qs = qs.filter(clinic__user_id=int(clinic_id))
            except ValueError:
                pass

        doctor_id = params.get('doctor_id')
        if doctor_id:
            try:
                qs = qs.filter(doctors__user_id=int(doctor_id))
            except ValueError:
                pass

        min_price = params.get('min_price')
        if min_price:
            try:
                qs = qs.filter(price__gte=float(min_price))
            except ValueError:
                pass

        max_price = params.get('max_price')
        if max_price:
            try:
                qs = qs.filter(price__lte=float(max_price))
            except ValueError:
                pass

        min_rating = params.get('min_rating')
        if min_rating:
            try:
                qs = qs.filter(clinic__rating__gte=float(min_rating))
            except ValueError:
                pass

        return qs


class ServiceDetailView(RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ServiceDetailSerializer
    queryset = Service.objects.filter(is_active=True).select_related('clinic').prefetch_related('doctors__user')
