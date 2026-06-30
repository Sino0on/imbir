from rest_framework import serializers

from appointments.models import Appointment
from reviews.models import Review
from services.models import Service
from users.models import ClinicBranch, ClinicInvite, ClinicProfile, DoctorClinicLink
from users.serializers import HybridImageField


class ClinicBranchUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicBranch
        fields = ('id', 'name', 'address', 'phone', 'schedule')
        read_only_fields = ('id',)


class ClinicInviteSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = ClinicInvite
        fields = ('id', 'branch', 'expires_at', 'is_active', 'is_valid', 'created_at')
        read_only_fields = ('id', 'is_valid', 'created_at')


class ClinicInviteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicInvite
        fields = ('branch', 'expires_at')

    def validate_branch(self, branch):
        clinic = self.context['clinic']
        if branch and branch.clinic_id != clinic.pk:
            raise serializers.ValidationError('Филиал не принадлежит этой клинике')
        return branch

    def create(self, validated_data):
        return ClinicInvite.objects.create(clinic=self.context['clinic'], **validated_data)


# ── Clinic Cabinet ──────────────────────────────────────────────────────────

class ClinicOwnProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    logo = HybridImageField(required=False, allow_null=True)
    branches = ClinicBranchUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicProfile
        fields = (
            'name', 'clinic_type', 'description', 'logo',
            'email', 'phone', 'website',
            'country', 'city', 'address', 'latitude', 'longitude',
            'schedule', 'lunch_break', 'emergency_24_7',
            'legal_name', 'reg_number', 'license_number', 'license_date', 'license_authority',
            'primary_specializations', 'narrow_specializations', 'additional_services',
            'equipment', 'patient_conditions', 'payment_methods',
            'experience_years', 'rating', 'reviews_count', 'doctors_count',
            'is_published', 'profile_views',
            'branches',
        )
        read_only_fields = ('rating', 'reviews_count', 'doctors_count', 'profile_views')


class ClinicAppointmentSerializer(serializers.ModelSerializer):
    doctor = serializers.SerializerMethodField()
    patient = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = ('id', 'date', 'time', 'is_online', 'status', 'notes',
                  'doctor', 'patient', 'service', 'created_at')

    def get_doctor(self, obj):
        if not obj.doctor:
            return None
        return {
            'id': obj.doctor.user.id,
            'full_name': obj.doctor.user.full_name,
        }

    def get_patient(self, obj):
        if obj.patient:
            return {
                'id': obj.patient.id,
                'full_name': obj.patient.full_name,
                'phone': obj.patient.phone,
            }
        return {'full_name': obj.guest_name, 'phone': obj.guest_phone}

    def get_service(self, obj):
        if not obj.service:
            return None
        return {'id': obj.service.id, 'name': obj.service.name, 'price': obj.service.price}


class ClinicDoctorSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='doctor.user.id')
    full_name = serializers.CharField(source='doctor.user.full_name')
    specialty = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    rating = serializers.DecimalField(source='doctor.rating', max_digits=3, decimal_places=2)
    appointments_total = serializers.SerializerMethodField()

    class Meta:
        model = DoctorClinicLink
        fields = ('id', 'full_name', 'specialty', 'photo', 'rating', 'appointments_total', 'is_active')

    def get_specialty(self, obj):
        specs = obj.doctor.primary_specializations
        return specs[0] if specs else ''

    def get_photo(self, obj):
        if not obj.doctor.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.doctor.photo.url) if request else obj.doctor.photo.url

    def get_appointments_total(self, obj):
        clinic = self.context.get('clinic')
        return Appointment.objects.filter(doctor=obj.doctor, clinic=clinic).count()


class ClinicServiceReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ('id', 'name', 'category', 'description', 'price', 'duration', 'is_active', 'created_at')


class ClinicServiceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ('name', 'category', 'description', 'price', 'duration', 'is_active')

    def create(self, validated_data):
        return Service.objects.create(clinic=self.context['clinic'], **validated_data)


class ClinicReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    reply = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ('id', 'author', 'rating', 'text', 'reply', 'created_at')

    def get_author(self, obj):
        return {
            'id': obj.author.id,
            'full_name': obj.author.full_name,
        }

    def get_reply(self, obj):
        if obj.reply_text:
            return {
                'text': obj.reply_text,
                'created_at': obj.reply_created_at,
            }
        return None
