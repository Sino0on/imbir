from rest_framework import serializers
from users.models import ClinicBranch, ClinicProfile


class ClinicBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicBranch
        fields = ('id', 'name', 'address', 'phone', 'schedule')


class ClinicListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    logo = serializers.SerializerMethodField()

    class Meta:
        model = ClinicProfile
        fields = (
            'id', 'name', 'logo', 'city', 'clinic_type',
            'rating', 'reviews_count', 'doctors_count',
            'primary_specializations',
        )

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url


class ClinicDetailSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    logo = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    doctors = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()
    branches = ClinicBranchSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicProfile
        fields = (
            'id', 'name', 'clinic_type', 'description',
            'logo', 'photos',
            'rating', 'reviews_count', 'doctors_count', 'experience_years',
            'country', 'city', 'address', 'website',
            'phone', 'email',
            'location',
            'schedule', 'lunch_break', 'emergency_24_7',
            'primary_specializations', 'narrow_specializations', 'additional_services',
            'equipment', 'patient_conditions', 'payment_methods',
            'branches', 'doctors', 'services',
        )

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url

    def get_photos(self, obj):
        request = self.context.get('request')
        result = []
        for photo in obj.photos.all():
            url = photo.image.url
            result.append(request.build_absolute_uri(url) if request else url)
        return result

    def get_location(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return None
        return {'lat': float(obj.latitude), 'lng': float(obj.longitude)}

    def get_doctors(self, obj):
        # Заглушка — будет заполнено при реализации связи клиника-врач
        return []

    def get_services(self, obj):
        # Заглушка — будет заполнено при реализации модуля услуг
        return []
