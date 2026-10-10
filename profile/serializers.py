from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, inline_serializer
from appointments.models import Appointment
from reviews.models import Review
from users.models import PatientProfile


class PatientProfileSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    patronymic = serializers.CharField(source='user.patronymic', required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(source='user.phone', required=False, allow_blank=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    avatar = serializers.SerializerMethodField()
    avatar_upload = serializers.ImageField(write_only=True, required=False)

    class Meta:
        model = PatientProfile
        fields = (
            'first_name', 'last_name', 'patronymic', 'email', 'phone',
            'avatar', 'avatar_upload',
            'blood_type', 'allergies',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relation',
        )

    def get_avatar(self, obj):
        if not obj.user.avatar:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.user.avatar.url) if request else obj.user.avatar.url

    def update(self, instance, validated_data):
        avatar_file = validated_data.pop('avatar_upload', None)
        user_data = validated_data.pop('user', {})

        user = instance.user
        for attr, value in user_data.items():
            setattr(user, attr, value)
        if avatar_file:
            user.avatar = avatar_file
        if user_data or avatar_file:
            user.save(update_fields=[*user_data.keys(), 'avatar'] if avatar_file else list(user_data.keys()))

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


def upcoming_cutoff():
    """Местные (date, time), раньше которых запись уже не «предстоящая».

    Запись остаётся в «Предстоящих», пока не закрылось окно подключения к
    онлайн-консультации (LIVEKIT_JOIN_WINDOW_MINUTES после начала): иначе
    опоздавший пациент не нашёл бы кнопку «Подключиться».
    """
    cutoff = timezone.localtime() - timedelta(minutes=settings.LIVEKIT_JOIN_WINDOW_MINUTES)
    return cutoff.date(), cutoff.time().replace(microsecond=0)


def upcoming_q():
    """Фильтр записей, время которых ещё не прошло (см. upcoming_cutoff)."""
    date, time = upcoming_cutoff()
    return Q(date__gt=date) | Q(date=date, time__gte=time)


class PatientAppointmentSerializer(serializers.ModelSerializer):
    doctor = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = (
            'id', 'date', 'time', 'status', 'notes',
            'is_online', 'google_meet_link',
            # Статус видео-консультации: по finished фронт прячет «Подключиться».
            'consultation_status',
            'diagnosis', 'recommendations',
            'doctor', 'clinic', 'service',
            'can_review', 'is_past', 'created_at',
        )
        read_only_fields = ('consultation_status',)

    def get_doctor(self, obj):
        if not obj.doctor:
            return None
        doctor = obj.doctor
        # Фото, специальность и рейтинг отдаём прямо в записи: раньше фронт
        # дочитывал их через /api/doctors/{id}/, а тот для снятого с публикации
        # врача отвечает 404 и на каждый просмотр накручивает profile_views.
        photo = None
        if doctor.photo:
            request = self.context.get('request')
            photo = request.build_absolute_uri(doctor.photo.url) if request else doctor.photo.url
        # .all(), а не .first(): так берётся из prefetch_related, без запроса на каждую запись.
        spec = next(iter(doctor.primary_specializations.all()), None)
        return {
            'id': doctor.user_id,
            'full_name': doctor.user.full_name,
            'photo': photo,
            'specialty': spec.name if spec else '',
            'rating': str(doctor.rating),
            'is_published': doctor.is_published,
        }

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        # Адрес того места, где проходит именно эта запись: филиал услуги, если
        # он указан, иначе основной адрес клиники (а не первой клиники врача).
        branch = obj.service.branch if obj.service else None
        address = (branch.address if branch else '') or obj.clinic.address
        return {
            'id': obj.clinic.user_id,
            'name': obj.clinic.name,
            'address': address,
        }

    def get_service(self, obj):
        if not obj.service:
            return None
        return {
            'id': obj.service.id,
            'name': obj.service.name,
            'price': obj.service.price,
            'duration': obj.service.duration,
        }

    def _reviewed_targets(self):
        """(doctor_ids, clinic_ids), которым пользователь уже оставил отзыв.

        Считается один раз на весь список: при many=True сериализатор записи
        один на все элементы, а context общий.
        """
        cache = self.context.setdefault('_reviewed_targets', {})
        if 'value' not in cache:
            request = self.context.get('request')
            user = getattr(request, 'user', None)
            if user is None or not user.is_authenticated:
                cache['value'] = (set(), set())
            else:
                rows = list(
                    Review.objects.filter(author=user).values_list('doctor_id', 'clinic_id')
                )
                cache['value'] = (
                    {doctor_id for doctor_id, _ in rows if doctor_id},
                    {clinic_id for _, clinic_id in rows if clinic_id},
                )
        return cache['value']

    @extend_schema_field(serializers.BooleanField)
    def get_can_review(self, obj):
        # То же правило, что в ReviewCreateSerializer: один отзыв на врача (на
        # клинику, если запись без врача) и только опубликованному. Раньше
        # смотрели лишь на отзыв к этой записи, и кнопка «Оставить отзыв» вела
        # к ошибке «Вы уже оставили отзыв этому врачу».
        if obj.status != Appointment.Status.COMPLETED:
            return False
        try:
            obj.review
            return False
        except Appointment.review.RelatedObjectDoesNotExist:
            pass
        reviewed_doctors, reviewed_clinics = self._reviewed_targets()
        if obj.doctor:
            return obj.doctor.is_published and obj.doctor_id not in reviewed_doctors
        if obj.clinic:
            return obj.clinic.is_published and obj.clinic_id not in reviewed_clinics
        return False

    @extend_schema_field(serializers.BooleanField)
    def get_is_past(self, obj):
        # Вкладка «Прошедшие»: завершённые, отменённые и те, чьё время уже прошло.
        if obj.status not in (Appointment.Status.PENDING, Appointment.Status.CONFIRMED):
            return True
        date, time = upcoming_cutoff()
        return (obj.date, obj.time) < (date, time)


from users.models import DoctorProfile, ClinicProfile
from services.models import Service

_FavoriteTargetClinicSerializer = inline_serializer('FavoriteTargetClinic', fields={
    'id': serializers.IntegerField(),
    'name': serializers.CharField(),
})


class FavoriteDoctorSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    full_name = serializers.CharField(source='user.full_name')
    specialty = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = ('id', 'full_name', 'specialty', 'photo', 'rating', 'experience_years', 'clinic')

    def get_specialty(self, obj):
        spec = obj.primary_specializations.first()
        return spec.name if spec else ''

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url

    @extend_schema_field(_FavoriteTargetClinicSerializer)
    def get_clinic(self, obj):
        link = obj.clinic_links.filter(is_active=True).select_related('clinic').first()
        if not link:
            return None
        return {'id': link.clinic.user_id, 'name': link.clinic.name}


class FavoriteClinicSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    logo = serializers.SerializerMethodField()

    class Meta:
        model = ClinicProfile
        fields = ('id', 'name', 'logo', 'city', 'clinic_type', 'rating')

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url


class FavoriteServiceSerializer(serializers.ModelSerializer):
    clinic = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = ('id', 'name', 'category', 'price', 'clinic')

    @extend_schema_field(_FavoriteTargetClinicSerializer)
    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        return {'id': obj.clinic.user_id, 'name': obj.clinic.name}


class FavoritesListSerializer(serializers.Serializer):
    doctors = FavoriteDoctorSerializer(source='favorite_doctors', many=True)
    clinics = FavoriteClinicSerializer(source='favorite_clinics', many=True)
    services = FavoriteServiceSerializer(source='favorite_services', many=True)


class FavoriteActionSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=['doctor', 'clinic', 'service'])
    target_id = serializers.IntegerField()

    def validate(self, data):
        t_type = data['target_type']
        t_id = data['target_id']

        if t_type == 'doctor':
            if not DoctorProfile.objects.filter(user_id=t_id, is_published=True).exists():
                raise serializers.ValidationError({'target_id': 'Врач не найден.'})
        elif t_type == 'clinic':
            if not ClinicProfile.objects.filter(user_id=t_id, is_published=True).exists():
                raise serializers.ValidationError({'target_id': 'Клиника не найдена.'})
        elif t_type == 'service':
            if not Service.objects.filter(id=t_id, is_active=True).exists():
                raise serializers.ValidationError({'target_id': 'Услуга не найдена.'})

        return data


class PatientReviewSerializer(serializers.ModelSerializer):
    target = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    reply = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ('id', 'target_type', 'target_id', 'target', 'rating', 'text', 'reply', 'created_at')

    def get_target(self, obj):
        if obj.target_type == Review.TargetType.DOCTOR and obj.doctor:
            return {
                'id': obj.doctor.user_id,
                'full_name': obj.doctor.user.full_name,
            }
        if obj.target_type == Review.TargetType.CLINIC and obj.clinic:
            return {
                'id': obj.clinic.user_id,
                'name': obj.clinic.name,
            }
        return None

    def get_target_id(self, obj):
        if obj.target_type == Review.TargetType.DOCTOR and obj.doctor:
            return obj.doctor.user_id
        elif obj.target_type == Review.TargetType.CLINIC and obj.clinic:
            return obj.clinic.user_id
        return None

    def get_reply(self, obj):
        if obj.reply_text:
            return {
                'text': obj.reply_text,
                'created_at': obj.reply_created_at,
            }
        return None
