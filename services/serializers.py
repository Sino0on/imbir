from rest_framework import serializers
from .models import Service


class ServiceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ('id', 'name', 'category', 'price', 'duration')


class ServiceDetailSerializer(serializers.ModelSerializer):
    clinic = serializers.SerializerMethodField()
    doctor = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            'id', 'name', 'category', 'description',
            'price', 'duration',
            'clinic', 'doctor',
        )

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        return {
            'id': obj.clinic.user_id,
            'name': obj.clinic.name,
        }

    def get_doctor(self, obj):
        if not obj.doctor:
            return None
        return {
            'id': obj.doctor.user_id,
            'full_name': obj.doctor.user.full_name,
        }
