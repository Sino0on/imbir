from rest_framework import serializers
from appointments.models import Appointment
from reviews.models import Review
from users.models import Favorite, PatientProfile


class PatientProfileSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    phone = serializers.CharField(source='user.phone', required=False, allow_blank=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    avatar = serializers.SerializerMethodField()
    avatar_upload = serializers.ImageField(write_only=True, required=False)

    class Meta:
        model = PatientProfile
        fields = (
            'first_name', 'last_name', 'email', 'phone',
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


class PatientAppointmentSerializer(serializers.ModelSerializer):
    doctor = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = (
            'id', 'date', 'time', 'status', 'notes',
            'doctor', 'clinic', 'service',
            'can_review', 'created_at',
        )

    def get_doctor(self, obj):
        if not obj.doctor:
            return None
        return {
            'id': obj.doctor.user_id,
            'full_name': obj.doctor.user.full_name,
        }

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        return {
            'id': obj.clinic.user_id,
            'name': obj.clinic.name,
        }

    def get_service(self, obj):
        if not obj.service:
            return None
        return {
            'id': obj.service.id,
            'name': obj.service.name,
            'price': obj.service.price,
        }

    def get_can_review(self, obj):
        if obj.status != Appointment.Status.COMPLETED:
            return False
        try:
            obj.review
            return False
        except Appointment.review.RelatedObjectDoesNotExist:
            return True


class FavoriteSerializer(serializers.ModelSerializer):
    target = serializers.SerializerMethodField()

    class Meta:
        model = Favorite
        fields = ('id', 'target_type', 'target_id', 'target', 'created_at')

    def get_target(self, obj):
        request = self.context.get('request')

        def abs_url(file_field):
            if not file_field:
                return None
            url = file_field.url
            return request.build_absolute_uri(url) if request else url

        if obj.target_type == Favorite.TargetType.DOCTOR:
            from users.models import DoctorProfile
            try:
                p = DoctorProfile.objects.select_related('user').get(user_id=obj.target_id)
                return {
                    'id': p.user_id,
                    'full_name': p.user.full_name,
                    'specialty': p.primary_specializations[0] if p.primary_specializations else '',
                    'photo': abs_url(p.photo),
                }
            except DoctorProfile.DoesNotExist:
                return None

        if obj.target_type == Favorite.TargetType.CLINIC:
            from users.models import ClinicProfile
            try:
                c = ClinicProfile.objects.get(user_id=obj.target_id)
                return {
                    'id': c.user_id,
                    'name': c.name,
                    'logo': abs_url(c.logo),
                }
            except ClinicProfile.DoesNotExist:
                return None

        if obj.target_type == Favorite.TargetType.SERVICE:
            from services.models import Service
            try:
                s = Service.objects.get(id=obj.target_id)
                return {
                    'id': s.id,
                    'name': s.name,
                    'category': s.category,
                    'price': s.price,
                }
            except Service.DoesNotExist:
                return None

        return None


class FavoriteCreateSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=Favorite.TargetType.values)
    target_id = serializers.IntegerField()

    def validate(self, data):
        from users.models import DoctorProfile, ClinicProfile
        from services.models import Service

        t_type = data['target_type']
        t_id = data['target_id']

        if t_type == Favorite.TargetType.DOCTOR:
            if not DoctorProfile.objects.filter(user_id=t_id, is_published=True).exists():
                raise serializers.ValidationError({'target_id': 'Врач не найден.'})
        elif t_type == Favorite.TargetType.CLINIC:
            if not ClinicProfile.objects.filter(user_id=t_id, is_published=True).exists():
                raise serializers.ValidationError({'target_id': 'Клиника не найдена.'})
        elif t_type == Favorite.TargetType.SERVICE:
            if not Service.objects.filter(id=t_id, is_active=True).exists():
                raise serializers.ValidationError({'target_id': 'Услуга не найдена.'})

        user = self.context['request'].user
        if Favorite.objects.filter(user=user, target_type=t_type, target_id=t_id).exists():
            raise serializers.ValidationError('Уже в избранном.')

        return data

    def create(self, validated_data):
        return Favorite.objects.create(user=self.context['request'].user, **validated_data)


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
