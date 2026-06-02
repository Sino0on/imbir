from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer

_LIST_RESPONSE = inline_serializer('NotificationListResponse', fields={
    'data': NotificationSerializer(many=True),
    'unread_count': serializers.IntegerField(),
})


@extend_schema(responses={200: _LIST_RESPONSE}, tags=['Notifications'])
class NotificationListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        unread_count = notifications.filter(is_read=False).count()
        serializer = NotificationSerializer(notifications, many=True)
        return Response({
            'data': serializer.data,
            'unread_count': unread_count,
        })


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
