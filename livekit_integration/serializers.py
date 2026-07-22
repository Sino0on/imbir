from rest_framework import serializers


class LiveKitTokenResponseSerializer(serializers.Serializer):
    url = serializers.CharField(help_text='WebSocket-адрес LiveKit сервера')
    room = serializers.CharField(help_text='Название комнаты консультации')
    token = serializers.CharField(help_text='JWT для подключения к комнате (TTL — 15 минут)')
