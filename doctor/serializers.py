from rest_framework import serializers
from appointments.models import Appointment
from reviews.models import Review
from services.models import Service
from references.models import Specialization
from references.serializers import SpecializationSerializer
from users.models import DoctorProfile, User
from doctors.serializers import InterviewSerializer
from doctors.models import Interview


from users.serializers import HybridImageField


class DoctorOwnProfileSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    email = serializers.EmailField(source='user.email', read_only=True)
    phone = serializers.CharField(source='user.phone', required=False, allow_blank=True)
    photo = HybridImageField(required=False, allow_null=True)
    documents = serializers.SerializerMethodField()
    interviews = InterviewSerializer(many=True, read_only=True)
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
        model = DoctorProfile
        fields = (
            # Личные данные
            'first_name', 'last_name', 'email', 'phone',
            'gender', 'birth_date', 'city', 'languages', 'photo',
            # Локация
            'country', 'address', 'website', 'latitude', 'longitude',
            # Расписание
            'schedule', 'lunch_break', 'emergency_24_7',
            # Юридические данные
            'legal_name', 'reg_number', 'license_number', 'license_date', 'license_authority',
            # Документы
            'documents',
            # Специализация
            'primary_specializations', 'primary_specialization_ids',
            'narrow_specializations', 'narrow_specialization_ids', 'additional_services',
            # Оборудование и условия
            'equipment', 'patient_conditions', 'payment_methods',
            # Публичный профиль
            'about', 'experience_years', 'is_online_available', 'consultation_price',
            # Профессиональные данные и образование. Храним отдельно от
            # work_experience: карточка врача не должна переписывать историю
            # мест работы ради правки текущей должности или допобразования.
            'position', 'qualification_category', 'academic_degree',
            'education', 'additional_education', 'work_experience', 'skills', 'interviews',
            # Статус и счётчики
            'is_published', 'profile_views', 'rating', 'reviews_count',
        )
        # is_published — читаем, но не пишем отсюда: полный PUT-профиль не должен
        # быть способом публикации/снятия с публикации (это модерационное поле,
        # меняется через админку). Иначе любое сохранение без явного is_published
        # в теле запроса тихо снимает врача с публикации (BooleanField в multipart
        # трактует отсутствие поля как False, а не как "оставить как было").
        read_only_fields = ('profile_views', 'rating', 'reviews_count', 'documents', 'interviews', 'is_published')


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

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        user = instance.user
        for attr, value in user_data.items():
            setattr(user, attr, value)
        if user_data:
            user.save(update_fields=list(user_data.keys()))

        primary_specializations = validated_data.pop('primary_specializations', None)
        narrow_specializations = validated_data.pop('narrow_specializations', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if primary_specializations is not None:
            instance.primary_specializations.set(primary_specializations)
        if narrow_specializations is not None:
            instance.narrow_specializations.set(narrow_specializations)
        return instance


class DoctorInterviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interview
        fields = ('id', 'title', 'video_url', 'priority')
        read_only_fields = ('id',)

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['doctor'] = request.user.doctor_profile
        return super().create(validated_data)


class DoctorScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorProfile
        fields = ('schedule', 'lunch_break', 'emergency_24_7')

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(update_fields=list(validated_data.keys()))
        return instance


class DoctorAppointmentSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = (
            'id', 'date', 'time', 'is_online', 'google_meet_link', 'status', 'notes',
            'patient', 'service', 'created_at',
        )

    def get_patient(self, obj):
        if obj.patient:
            return {
                'id': obj.patient.id,
                'full_name': obj.patient.full_name,
                'phone': obj.patient.phone,
                'email': obj.patient.email,
            }
        return {
            'full_name': obj.guest_name,
            'phone': obj.guest_phone,
            'email': obj.guest_email,
        }

    def get_service(self, obj):
        if not obj.service:
            return None
        return {
            'id': obj.service.id,
            'name': obj.service.name,
            'price': obj.service.price,
        }


class DoctorPatientSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField()
    visits_count = serializers.IntegerField()
    last_visit = serializers.DateField()
    diagnosis = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'full_name', 'phone', 'email', 'visits_count', 'last_visit', 'diagnosis')

    def get_diagnosis(self, obj):
        doctor_profile = self.context.get('doctor_profile')
        if not doctor_profile:
            request = self.context.get('request')
            if request and request.user.is_authenticated:
                doctor_profile = getattr(request.user, 'doctor_profile', None)
        if not doctor_profile:
            return ""
        
        latest_appt = (
            Appointment.objects
            .filter(patient=obj, doctor=doctor_profile)
            .exclude(diagnosis="")
            .exclude(diagnosis__isnull=True)
            .order_by('-date', '-time')
            .first()
        )
        return latest_appt.diagnosis if latest_appt else ""


class DoctorAppointmentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ('diagnosis', 'recommendations', 'doctor_notes')


class DoctorReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    reply = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ('id', 'author', 'rating', 'text', 'reply', 'created_at')

    def get_author(self, obj):
        return {'id': obj.author.id, 'full_name': obj.author.full_name}

    def get_reply(self, obj):
        if obj.reply_text:
            return {
                'text': obj.reply_text,
                'created_at': obj.reply_created_at,
            }
        return None


class DoctorServiceReadSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            'id', 'name', 'category', 'description', 'price', 'duration', 'photo',
            'schedule', 'lunch_break', 'is_active', 'created_at',
        )

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url


class DoctorServiceWriteSerializer(serializers.ModelSerializer):
    photo = HybridImageField(required=False, allow_null=True)
    # Явный default: BooleanField в multipart/form-data трактует отсутствие поля как
    # "чекбокс не отмечен" -> False, а не как "использовать default модели" (True).
    # Актуально именно тут, т.к. photo делает multipart нормой, а не исключением.
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Service
        fields = ('name', 'category', 'description', 'price', 'duration', 'photo', 'schedule', 'lunch_break', 'is_active')

    def create(self, validated_data):
        doctor = self.context['doctor']
        service = Service.objects.create(**validated_data)
        doctor.services.add(service)
        return service
