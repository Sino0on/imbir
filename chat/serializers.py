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


class RecoDoctorSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='user_id')
    full_name = serializers.CharField(source='user.full_name')
    specialty = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    is_online_available = serializers.BooleanField()

    def get_specialty(self, obj):
        specs = obj.primary_specializations
        return specs[0] if specs else ''

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url


class RecoClinicSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='user_id')
    name = serializers.CharField()
    logo = serializers.SerializerMethodField()
    city = serializers.CharField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url


class RecoServiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    clinic = serializers.SerializerMethodField()

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        return {'id': obj.clinic.user_id, 'name': obj.clinic.name}


class AIMessageSerializer(serializers.ModelSerializer):
    recommendations = serializers.SerializerMethodField()

    class Meta:
        model = AIMessage
        fields = ('id', 'role', 'content', 'recommendations', 'created_at')

    def get_recommendations(self, obj):
        from .recommendations import serialize_recommendations
        return serialize_recommendations(obj.recommendations, self.context.get('request'))


class SendAIMessageSerializer(serializers.Serializer):
    message = serializers.CharField()
