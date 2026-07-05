from rest_framework import serializers
from .models import Service


class ServiceListSerializer(serializers.ModelSerializer):
    clinic = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = ('id', 'name', 'category', 'price', 'duration',
                  'clinic', 'rating', 'reviews_count', 'photo')

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        c = obj.clinic
        request = self.context.get('request')
        logo_url = None
        if c.logo:
            logo_url = request.build_absolute_uri(c.logo.url) if request else c.logo.url
        return {
            'id': c.user_id,
            'name': c.name,
            'logo': logo_url,
        }

    def get_rating(self, obj):
        # Приоритет: рейтинг клиники → первого врача
        if obj.clinic:
            return float(obj.clinic.rating)
        first = obj.doctors.first()
        return float(first.rating) if first else 0.0

    def get_reviews_count(self, obj):
        if obj.clinic:
            return obj.clinic.reviews_count
        first = obj.doctors.first()
        return first.reviews_count if first else 0

    def get_photo(self, obj):
        # Фото первого врача из списка
        first = obj.doctors.first()
        if not first or not first.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(first.photo.url) if request else first.photo.url



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
