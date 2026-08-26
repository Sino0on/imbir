from rest_framework import serializers

from appointments.models import Appointment
from reviews.models import Review
from services.models import Service
from references.models import Specialization
from references.serializers import SpecializationSerializer
from users.models import ClinicBranch, ClinicInvite, ClinicProfile, DoctorClinicLink, DoctorProfile
from users.serializers import HybridImageField

# Поля профиля врача, которые заполняет клиника при найме (не логин/график/цена приёма —
# это остаётся в зоне ответственности самого врача через /api/doctor/profile/).
_CLINIC_DOCTOR_PROFILE_FIELDS = (
    # Основная информация
    'gender', 'birth_date', 'city', 'languages', 'photo',
    # Профессиональные данные
    'primary_specializations', 'primary_specialization_ids',
    'narrow_specializations', 'narrow_specialization_ids',
    'experience_years', 'position', 'qualification_category', 'academic_degree',
    # Образование
    'education', 'additional_education',
    # Документы
    'license_number',
)


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
    photos = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    primary_specializations = SpecializationSerializer(many=True, read_only=True)
    primary_specialization_ids = serializers.PrimaryKeyRelatedField(
        source='primary_specializations', many=True, write_only=True, required=False, default=list,
        queryset=Specialization.objects.all(),
    )
    narrow_specializations = SpecializationSerializer(many=True, read_only=True)
    narrow_specialization_ids = serializers.PrimaryKeyRelatedField(
        source='narrow_specializations', many=True, write_only=True, required=False, default=list,
        queryset=Specialization.objects.all(),
    )

    class Meta:
        model = ClinicProfile
        fields = (
            'name', 'clinic_type', 'description', 'logo',
            'email', 'phone', 'website',
            'country', 'city', 'address', 'latitude', 'longitude',
            'schedule', 'lunch_break', 'emergency_24_7',
            'legal_name', 'reg_number', 'license_number', 'license_date', 'license_authority',
            'documents',
            'primary_specializations', 'primary_specialization_ids',
            'narrow_specializations', 'narrow_specialization_ids', 'additional_services',
            'equipment', 'patient_conditions', 'payment_methods',
            'experience_years', 'rating', 'reviews_count', 'doctors_count',
            'is_published', 'profile_views',
            'branches',
            'photos',
        )
        read_only_fields = ('rating', 'reviews_count', 'doctors_count', 'profile_views', 'photos', 'documents')

    def get_photos(self, obj):
        request = self.context.get('request')
        return [
            {
                'id': p.id,
                'url': request.build_absolute_uri(p.image.url) if request else p.image.url,
                'uploaded_at': p.uploaded_at,
            }
            for p in obj.photos.all().order_by('uploaded_at')
        ]

    def get_documents(self, obj):
        request = self.context.get('request')
        return [
            {
                'id': d.id,
                'url': request.build_absolute_uri(d.file.url) if request else d.file.url,
                'uploaded_at': d.uploaded_at,
            }
            for d in obj.documents.all().order_by('uploaded_at')
        ]


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
        spec = obj.doctor.primary_specializations.first()
        return spec.name if spec else ''

    def get_photo(self, obj):
        if not obj.doctor.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.doctor.photo.url) if request else obj.doctor.photo.url

    def get_appointments_total(self, obj):
        clinic = self.context.get('clinic')
        return Appointment.objects.filter(doctor=obj.doctor, clinic=clinic).count()


class ClinicDoctorProfileSerializer(serializers.ModelSerializer):
    """Полная карточка уже прикреплённого к клинике врача — просмотр (GET) и правка
    (PATCH) полей, которые заполняет клиника при найме. Логин (email/пароль) и график
    приёма сюда не входят — это меняет только сам врач через /api/doctor/profile/."""
    id = serializers.IntegerField(source='user.id', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    patronymic = serializers.CharField(source='user.patronymic', read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    photo = HybridImageField(required=False, allow_null=True)

    primary_specializations = SpecializationSerializer(many=True, read_only=True)
    primary_specialization_ids = serializers.PrimaryKeyRelatedField(
        source='primary_specializations', many=True, write_only=True, required=False,
        queryset=Specialization.objects.all(),
    )
    narrow_specializations = SpecializationSerializer(many=True, read_only=True)
    narrow_specialization_ids = serializers.PrimaryKeyRelatedField(
        source='narrow_specializations', many=True, write_only=True, required=False,
        queryset=Specialization.objects.all(),
    )
    documents = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = (
            'id', 'first_name', 'last_name', 'patronymic', 'full_name', 'email', 'phone',
        ) + _CLINIC_DOCTOR_PROFILE_FIELDS + ('documents',)
        read_only_fields = ('id', 'first_name', 'last_name', 'patronymic', 'full_name', 'email', 'phone')

    def get_documents(self, obj):
        request = self.context.get('request')
        return [{
            'id': d.id,
            'url': request.build_absolute_uri(d.file.url) if request else d.file.url,
            'uploaded_at': d.uploaded_at,
        } for d in obj.documents.all().order_by('uploaded_at')]


class ClinicServiceBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicBranch
        fields = ('id', 'name', 'address')


class ClinicServiceReadSerializer(serializers.ModelSerializer):
    doctors = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    branch = ClinicServiceBranchSerializer(read_only=True)

    class Meta:
        model = Service
        fields = (
            'id', 'name', 'category', 'description', 'price', 'duration', 'photo',
            'branch', 'schedule', 'lunch_break', 'is_active', 'doctors', 'created_at',
        )

    def get_doctors(self, obj):
        return [
            {
                'id': d.user_id,
                'full_name': d.user.full_name
            }
            for d in obj.doctors.all()
        ]

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url


class ClinicServiceWriteSerializer(serializers.ModelSerializer):
    doctor_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True
    )
    photo = HybridImageField(required=False, allow_null=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        source='branch', queryset=ClinicBranch.objects.all(), required=False, allow_null=True,
    )
    # Явный default: BooleanField в multipart/form-data трактует отсутствие поля как
    # "чекбокс не отмечен" -> False, а не как "использовать default модели" (True).
    # На partial-обновлениях (PUT здесь всегда идёт с partial=True) не мешает —
    # DRF не подставляет default полям, которых нет во входных данных.
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Service
        fields = (
            'name', 'category', 'description', 'price', 'duration', 'photo',
            'branch_id', 'schedule', 'lunch_break', 'is_active', 'doctor_ids',
        )

    def validate_doctor_ids(self, value):
        if not value:
            return value
        clinic = self.context['clinic']
        from users.models import DoctorClinicLink
        linked_docs = set(
            DoctorClinicLink.objects.filter(clinic=clinic, doctor__user_id__in=value)
            .values_list('doctor__user_id', flat=True)
        )
        invalid_docs = set(value) - linked_docs
        if invalid_docs:
            raise serializers.ValidationError(
                f'Некоторые врачи не принадлежат этой клинике или не найдены: {list(invalid_docs)}'
            )
        return value

    def validate_branch_id(self, value):
        if value is None:
            return value
        clinic = self.context['clinic']
        if value.clinic_id != clinic.id:
            raise serializers.ValidationError('Этот филиал не принадлежит вашей клинике.')
        return value

    def create(self, validated_data):
        doctor_ids = validated_data.pop('doctor_ids', [])
        clinic = self.context['clinic']
        service = Service.objects.create(clinic=clinic, **validated_data)

        if doctor_ids:
            from users.models import DoctorProfile
            doctors = DoctorProfile.objects.filter(user_id__in=doctor_ids)
            for doctor in doctors:
                doctor.services.add(service)

        return service

    def update(self, instance, validated_data):
        doctor_ids = validated_data.pop('doctor_ids', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if doctor_ids is not None:
            from users.models import DoctorProfile
            new_doctors = DoctorProfile.objects.filter(user_id__in=doctor_ids)
            instance.doctors.set(new_doctors)

        return instance


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


class ClinicDoctorCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    password = serializers.CharField(max_length=128, required=False, default='Doctor123!', write_only=True)

    # Основная информация — опционально, можно дополнить/поправить позже через PATCH
    gender = serializers.CharField(required=False, allow_blank=True, default='')
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    city = serializers.CharField(required=False, allow_blank=True, default='')
    languages = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    photo = HybridImageField(required=False, allow_null=True)

    # Профессиональные данные
    primary_specialization_ids = serializers.PrimaryKeyRelatedField(
        source='primary_specializations', many=True, required=False, default=list,
        queryset=Specialization.objects.all(),
    )
    narrow_specialization_ids = serializers.PrimaryKeyRelatedField(
        source='narrow_specializations', many=True, required=False, default=list,
        queryset=Specialization.objects.all(),
    )
    experience_years = serializers.IntegerField(required=False, default=0)
    position = serializers.CharField(required=False, allow_blank=True, default='')
    qualification_category = serializers.CharField(required=False, allow_blank=True, default='')
    academic_degree = serializers.CharField(required=False, allow_blank=True, default='')

    # Образование
    education = serializers.ListField(required=False, default=list)
    additional_education = serializers.ListField(required=False, default=list)

    # Документы
    license_number = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_email(self, value):
        from users.models import User
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Пользователь с такой почтой уже существует.')
        return value

    def validate_phone(self, value):
        if value:
            from users.models import User
            if User.objects.filter(phone=value).exists():
                raise serializers.ValidationError('Пользователь с таким номером телефона уже существует.')
        return value

    def create(self, validated_data):
        from users.models import User, DoctorProfile, DoctorClinicLink
        clinic = self.context['clinic']

        user = User.objects.create_user(
            email=validated_data['email'],
            phone=validated_data.get('phone') or None,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password'],
            role=User.Role.DOCTOR
        )

        doctor_profile = DoctorProfile.objects.create(
            user=user,
            city=validated_data.get('city') or clinic.city,
            country=clinic.country,
            is_published=True,
            gender=validated_data.get('gender', ''),
            birth_date=validated_data.get('birth_date'),
            languages=validated_data.get('languages') or [],
            photo=validated_data.get('photo'),
            experience_years=validated_data.get('experience_years') or 0,
            position=validated_data.get('position', ''),
            qualification_category=validated_data.get('qualification_category', ''),
            academic_degree=validated_data.get('academic_degree', ''),
            education=validated_data.get('education') or [],
            additional_education=validated_data.get('additional_education') or [],
            license_number=validated_data.get('license_number', ''),
        )
        doctor_profile.primary_specializations.set(validated_data.get('primary_specializations') or [])
        doctor_profile.narrow_specializations.set(validated_data.get('narrow_specializations') or [])

        link = DoctorClinicLink.objects.create(
            doctor=doctor_profile,
            clinic=clinic
        )
        return link
