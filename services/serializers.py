from rest_framework import serializers
from .models import Service


class ServiceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ('id', 'name', 'category', 'price', 'duration')


class ServiceDoctorSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user_id')
    full_name = serializers.CharField(source='user.full_name')
    photo = serializers.SerializerMethodField()

    class Meta:
        from users.models import DoctorProfile
        model = DoctorProfile
        fields = ('id', 'full_name', 'photo')

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url


class ServiceDetailSerializer(serializers.ModelSerializer):
    clinic = serializers.SerializerMethodField()
    doctor = serializers.SerializerMethodField()
    doctors = ServiceDoctorSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = (
            'id', 'name', 'category', 'description',
            'price', 'duration',
            'clinic', 'doctor', 'doctors',
        )

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        return {
            'id': obj.clinic.user_id,
            'name': obj.clinic.name,
        }

    def get_doctor(self, obj):
        first_doc = obj.doctors.first()
        if not first_doc:
            return None
        return {
            'id': first_doc.user_id,
            'full_name': first_doc.user.full_name,
        }
