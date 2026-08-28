from django.db.models import Count
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardPagination
from .models import Notification
from .serializers import NotificationSerializer


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='is_read', type=bool, required=False,
            description='Фильтр по статусу прочтения — ?is_read=false (только непрочитанные) или true.',
        ),
    ],
    tags=['Notifications'],
    summary='Список уведомлений (с пагинацией)',
)
class NotificationListView(ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = NotificationSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        is_read = self.request.query_params.get('is_read', '').strip().lower()
        if is_read in ('true', '1'):
            qs = qs.filter(is_read=True)
        elif is_read in ('false', '0'):
            qs = qs.filter(is_read=False)
        return qs


@extend_schema(
    responses={200: inline_serializer('NotificationUnreadCountResponse', fields={
        'total': serializers.IntegerField(),
        'by_type': serializers.DictField(child=serializers.IntegerField()),
    })},
    tags=['Notifications'],
    summary='Количество непрочитанных уведомлений, с разбивкой по типу',
)
class NotificationUnreadCountView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        qs = Notification.objects.filter(user=request.user, is_read=False)
        by_type = {
            row['type']: row['count']
            for row in qs.values('type').annotate(count=Count('id'))
        }
        return Response({'total': sum(by_type.values()), 'by_type': by_type})


@extend_schema(request=None, responses={200: NotificationSerializer}, tags=['Notifications'])
class NotificationMarkReadView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response({'detail': 'Не найдено'}, status=status.HTTP_404_NOT_FOUND)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)


@extend_schema(
    request=None,
    responses={200: inline_serializer('ReadAllResponse', fields={'marked_read': serializers.IntegerField()})},
    tags=['Notifications'],
)
class NotificationMarkAllReadView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'marked_read': count})
