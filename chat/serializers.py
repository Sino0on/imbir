from rest_framework import serializers
from .models import ChatRoom, ChatMessage, AIMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    sender = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ('id', 'sender', 'content', 'created_at', 'is_read')

    def get_sender(self, obj):
        if not obj.sender:
            return None
        return {'id': obj.sender.id, 'full_name': obj.sender.full_name}


class ChatRoomSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = ('id', 'participants', 'last_message', 'created_at')

    def get_participants(self, obj):
        return [{'id': u.id, 'full_name': u.full_name} for u in obj.participants.all()]

    def get_last_message(self, obj):
        msg = obj.messages.last()
        if not msg:
            return None
        return {'content': msg.content, 'created_at': msg.created_at}


class CreateRoomSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()


class AIMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = ('id', 'role', 'content', 'created_at')


class SendAIMessageSerializer(serializers.Serializer):
    message = serializers.CharField()
