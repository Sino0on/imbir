from rest_framework import serializers
from users.models import DoctorProfile, ClinicProfile
from services.models import Service


class SuggestDoctorSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    full_name = serializers.CharField(source='user.full_name')
    specialty = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = ('id', 'full_name', 'specialty', 'photo')

    def get_specialty(self, obj):
        specs = obj.primary_specializations
        return specs[0] if specs else ''

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url


class SuggestClinicSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    logo = serializers.SerializerMethodField()

    class Meta:
        model = ClinicProfile
        fields = ('id', 'name', 'logo')

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url


class SuggestServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ('id', 'name', 'price', 'category')
