from rest_framework import serializers
from users.models import DoctorProfile


class DoctorDetailSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    full_name = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    phone = serializers.CharField(source='user.phone')
    email = serializers.EmailField(source='user.email')
    location = serializers.SerializerMethodField()
    workplaces = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = (
            'id', 'full_name', 'specialty', 'photo',
            'rating', 'reviews_count', 'experience_years',
            'is_online_available', 'city', 'languages', 'about',
            'education', 'work_experience', 'skills',
            'primary_specializations', 'narrow_specializations',
            'workplaces',
            'equipment', 'patient_conditions', 'payment_methods',
            'phone', 'email', 'location',
        )

    def get_full_name(self, obj):
        return obj.user.full_name

    def get_specialty(self, obj):
        specs = obj.primary_specializations
        return specs[0] if specs else ''

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url

    def get_location(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return None
        return {'lat': float(obj.latitude), 'lng': float(obj.longitude)}

    def get_workplaces(self, obj):
        # Заглушка — будет заполнено при реализации модуля клиник
        return []


class DoctorListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    full_name = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    reviews_count = serializers.IntegerField()
    experience_years = serializers.IntegerField()
    is_online_available = serializers.BooleanField()
    city = serializers.CharField()
    # workplaces будут добавлены при реализации модуля клиник
    workplaces = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = (
            'id', 'full_name', 'specialty', 'photo',
            'rating', 'reviews_count', 'experience_years',
            'is_online_available', 'city', 'workplaces',
        )

    def get_full_name(self, obj):
        return obj.user.full_name

    def get_specialty(self, obj):
        specs = obj.primary_specializations
        return specs[0] if specs else ''

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url

    def get_workplaces(self, obj):
        # Заглушка до реализации модуля клиник
        return []
