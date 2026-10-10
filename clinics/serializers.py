from rest_framework import serializers
from references.serializers import SpecializationSerializer
from users.models import ClinicBranch, ClinicProfile


class ClinicBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicBranch
        fields = ('id', 'name', 'address', 'phone', 'schedule')


class ClinicListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    logo = serializers.SerializerMethodField()
    primary_specializations = SpecializationSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicProfile
        fields = (
            'id', 'name', 'logo', 'city', 'address', 'clinic_type', 'experience_years',
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
    primary_specializations = SpecializationSerializer(many=True, read_only=True)
    narrow_specializations = SpecializationSerializer(many=True, read_only=True)

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
        # Порядок загрузки: первое фото — главный баннер страницы клиники.
        # Сортируем в Python, чтобы не терять prefetch_related('photos').
        for photo in sorted(obj.photos.all(), key=lambda p: (p.uploaded_at, p.id)):
            url = photo.image.url
            result.append(request.build_absolute_uri(url) if request else url)
        return result

    def get_location(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return None
        return {'lat': float(obj.latitude), 'lng': float(obj.longitude)}

    def get_doctors(self, obj):
        request = self.context.get('request')
        links = obj.doctor_links.filter(is_active=True).select_related(
            'doctor', 'doctor__user',
        )
        result = []
        for link in links:
            doc = link.doctor
            photo_url = None
            if doc.photo:
                photo_url = (
                    request.build_absolute_uri(doc.photo.url)
                    if request else doc.photo.url
                )
            spec = doc.primary_specializations.first()
            result.append({
                'id': doc.user_id,
                'full_name': doc.user.full_name,
                'photo': photo_url,
                'specialty': spec.name if spec else '',
                'rating': float(doc.rating),
                'experience_years': doc.experience_years,
            })
        return result

    def get_services(self, obj):
        services = obj.services.filter(is_active=True)
        result = []
        for svc in services:
            result.append({
                'id': svc.id,
                'name': svc.name,
                'category': svc.category,
                'price': str(svc.price) if svc.price is not None else None,
                'duration': svc.duration,
            })
        return result
