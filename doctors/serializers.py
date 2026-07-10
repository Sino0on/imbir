from rest_framework import serializers
from users.models import DoctorProfile
from .models import Interview


class InterviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interview
        fields = ('id', 'title', 'video_url', 'priority')


class DoctorDetailSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    full_name = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    phone = serializers.CharField(source='user.phone')
    email = serializers.EmailField(source='user.email')
    location = serializers.SerializerMethodField()
    workplaces = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()
    interviews = InterviewSerializer(many=True, read_only=True)

    class Meta:
        model = DoctorProfile
        fields = (
            'id', 'full_name', 'specialty', 'photo',
            'rating', 'reviews_count', 'experience_years',
            'is_online_available', 'city', 'languages', 'about',
            'education', 'work_experience', 'skills',
            'primary_specializations', 'narrow_specializations',
            'workplaces', 'clinic',
            'equipment', 'patient_conditions', 'payment_methods',
            'phone', 'email', 'location', 'interviews',
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
        request = self.context.get('request')
        links = obj.clinic_links.filter(is_active=True).select_related('clinic')
        result = []
        for link in links:
            clinic = link.clinic
            logo_url = None
            if clinic.logo:
                logo_url = (
                    request.build_absolute_uri(clinic.logo.url)
                    if request else clinic.logo.url
                )
            result.append({
                'id': clinic.user_id,
                'name': clinic.name,
                'logo': logo_url,
                'address': clinic.address,
            })
        return result

    def get_clinic(self, obj):
        request = self.context.get('request')
        link = obj.clinic_links.filter(is_active=True).select_related('clinic').first()
        if not link:
            return None
        clinic = link.clinic
        logo_url = None
        if clinic.logo:
            logo_url = (
                request.build_absolute_uri(clinic.logo.url)
                if request else clinic.logo.url
            )
        return {
            'id': clinic.user_id,
            'name': clinic.name,
            'logo': logo_url,
            'address': clinic.address,
        }


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
    workplaces = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = (
            'id', 'full_name', 'specialty', 'photo',
            'rating', 'reviews_count', 'experience_years',
            'is_online_available', 'city', 'workplaces', 'clinic',
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
        request = self.context.get('request')
        links = obj.clinic_links.filter(is_active=True).select_related('clinic')
        result = []
        for link in links:
            clinic = link.clinic
            logo_url = None
            if clinic.logo:
                logo_url = (
                    request.build_absolute_uri(clinic.logo.url)
                    if request else clinic.logo.url
                )
            result.append({
                'id': clinic.user_id,
                'name': clinic.name,
                'logo': logo_url,
                'address': clinic.address,
            })
        return result

    def get_clinic(self, obj):
        request = self.context.get('request')
        link = obj.clinic_links.filter(is_active=True).select_related('clinic').first()
        if not link:
            return None
        clinic = link.clinic
        logo_url = None
        if clinic.logo:
            logo_url = (
                request.build_absolute_uri(clinic.logo.url)
                if request else clinic.logo.url
            )
        return {
            'id': clinic.user_id,
            'name': clinic.name,
            'logo': logo_url,
            'address': clinic.address,
        }
