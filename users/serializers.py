from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import ClinicBranch, ClinicInvite, DoctorClinicLink, User, DoctorProfile, ClinicProfile
from users.utils import get_relative_path_from_url

class HybridImageField(serializers.ImageField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            if not data.strip():
                return None
            return get_relative_path_from_url(data)
        return super().to_internal_value(data)

    def to_representation(self, value):
        if not value:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(value.url) if request else value.url

class HybridFileField(serializers.FileField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            if not data.strip():
                return None
            return get_relative_path_from_url(data)
        return super().to_internal_value(data)

    def to_representation(self, value):
        if not value:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(value.url) if request else value.url


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError('Неверный email или пароль')
        if not user.is_active:
            raise serializers.ValidationError('Аккаунт отключён')
        data['user'] = user
        return data


class ClientRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password', 'phone')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Пользователь с таким email уже существует')
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=validated_data.get('phone', ''),
            role=User.Role.PATIENT,
        )


class UserMeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'full_name', 'phone', 'avatar', 'role', 'date_joined')
        read_only_fields = ('id', 'email', 'full_name', 'role', 'date_joined')

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class _LocationSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True, default=None)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True, default=None)


class DoctorStep1Serializer(serializers.Serializer):
    full_name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True, default='')
    gender = serializers.CharField(required=False, allow_blank=True, default='')
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    city = serializers.CharField(required=False, allow_blank=True, default='')
    languages = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class DoctorStep2Serializer(serializers.Serializer):
    country = serializers.CharField(required=False, allow_blank=True, default='')
    city = serializers.CharField(required=False, allow_blank=True, default='')
    address = serializers.CharField(required=False, allow_blank=True, default='')
    phone = serializers.CharField(required=False, allow_blank=True, default='')
    website = serializers.URLField(required=False, allow_blank=True, default='')
    location = _LocationSerializer(required=False, allow_null=True, default=None)


class DoctorStep3Serializer(serializers.Serializer):
    schedule = serializers.DictField(required=False, default=dict)
    lunch_break = serializers.DictField(required=False, default=dict)
    emergency_24_7 = serializers.BooleanField(default=False)


class DoctorStep4Serializer(serializers.Serializer):
    legal_name = serializers.CharField(required=False, allow_blank=True, default='')
    reg_number = serializers.CharField(required=False, allow_blank=True, default='')
    license_number = serializers.CharField(required=False, allow_blank=True, default='')
    license_date = serializers.DateField(required=False, allow_null=True, default=None)
    license_authority = serializers.CharField(required=False, allow_blank=True, default='')


class DoctorStep5Serializer(serializers.Serializer):
    primary_specializations = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    narrow_specializations = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    additional_services = serializers.CharField(required=False, allow_blank=True, default='')


class DoctorStep6Serializer(serializers.Serializer):
    equipment = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    patient_conditions = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    payment_methods = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class DoctorStep7Serializer(serializers.Serializer):
    agree_terms = serializers.BooleanField()
    agree_privacy = serializers.BooleanField()
    agree_data_processing = serializers.BooleanField()
    agree_publishing = serializers.BooleanField()


class DoctorRegisterSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)
    step1 = DoctorStep1Serializer()
    step2 = DoctorStep2Serializer()
    step3 = DoctorStep3Serializer()
    step4 = DoctorStep4Serializer()
    step5 = DoctorStep5Serializer()
    step6 = DoctorStep6Serializer()
    step7 = DoctorStep7Serializer()
    photo = HybridImageField(required=False, allow_null=True)
    invite_clinic_id = serializers.IntegerField(required=False, allow_null=True)
    invite_branch_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        s1 = data['step1']
        s7 = data['step7']

        if User.objects.filter(email=s1['email']).exists():
            raise serializers.ValidationError({'step1': {'email': 'Пользователь с таким email уже существует'}})

        for field, msg in [
            ('agree_terms', 'Необходимо принять условия использования'),
            ('agree_privacy', 'Необходимо принять политику конфиденциальности'),
            ('agree_data_processing', 'Необходимо дать согласие на обработку данных'),
            ('agree_publishing', 'Необходимо дать согласие на публикацию'),
        ]:
            if not s7.get(field):
                raise serializers.ValidationError({'step7': msg})

        invite_clinic_id = data.get('invite_clinic_id')
        if invite_clinic_id:
            qs = ClinicInvite.objects.select_related('clinic', 'branch').filter(
                clinic__user_id=invite_clinic_id,
                is_active=True,
            )
            invite_branch_id = data.get('invite_branch_id')
            if invite_branch_id:
                qs = qs.filter(branch_id=invite_branch_id)
            invite = qs.order_by('-created_at').first()
            if not invite:
                raise serializers.ValidationError({'invite_clinic_id': 'Активный инвайт для клиники не найден'})
            if not invite.is_valid:
                raise serializers.ValidationError({'invite_clinic_id': 'Инвайт истёк'})
            data['_invite'] = invite
        else:
            data['_invite'] = None

        return data

    def create(self, validated_data):
        from django.db import transaction

        s1 = validated_data['step1']
        s2 = validated_data['step2']
        s3 = validated_data['step3']
        s4 = validated_data['step4']
        s5 = validated_data['step5']
        s6 = validated_data['step6']
        s7 = validated_data['step7']
        invite = validated_data.get('_invite')

        full_name_parts = s1['full_name'].strip().split()
        last_name = full_name_parts[0] if len(full_name_parts) > 0 else ''
        first_name = full_name_parts[1] if len(full_name_parts) > 1 else ''

        location = s2.get('location') or {}

        with transaction.atomic():
            user = User.objects.create_user(
                email=s1['email'],
                password=validated_data['password'],
                first_name=first_name,
                last_name=last_name,
                phone=s1.get('phone', ''),
                role=User.Role.DOCTOR,
            )

            DoctorProfile.objects.create(
                user=user,
                gender=s1.get('gender', ''),
                birth_date=s1.get('birth_date'),
                city=s1.get('city', ''),
                languages=s1.get('languages', []),
                photo=validated_data.get('photo'),
                country=s2.get('country', ''),
                address=s2.get('address', ''),
                website=s2.get('website', ''),
                latitude=location.get('lat') if isinstance(location, dict) else None,
                longitude=location.get('lng') if isinstance(location, dict) else None,
                schedule=s3.get('schedule', {}),
                lunch_break=s3.get('lunch_break', {}),
                emergency_24_7=s3.get('emergency_24_7', False),
                legal_name=s4.get('legal_name', ''),
                reg_number=s4.get('reg_number', ''),
                license_number=s4.get('license_number', ''),
                license_date=s4.get('license_date'),
                license_authority=s4.get('license_authority', ''),
                primary_specializations=s5.get('primary_specializations', []),
                narrow_specializations=s5.get('narrow_specializations', []),
                additional_services=s5.get('additional_services', ''),
                equipment=s6.get('equipment', []),
                patient_conditions=s6.get('patient_conditions', []),
                payment_methods=s6.get('payment_methods', []),
                agree_terms=s7['agree_terms'],
                agree_privacy=s7['agree_privacy'],
                agree_data_processing=s7['agree_data_processing'],
                agree_publishing=s7['agree_publishing'],
            )

            if invite:
                DoctorClinicLink.objects.create(
                    doctor=user.doctor_profile,
                    clinic=invite.clinic,
                    branch=invite.branch,
                )

        return user


def _parse_step(value, field_name):
    import json
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        raise serializers.ValidationError({field_name: 'Ожидается JSON-строка'})


class ClinicRegisterSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)
    step1 = serializers.CharField()
    step2 = serializers.CharField()
    step3 = serializers.CharField()
    step4 = serializers.CharField()
    step5 = serializers.CharField()
    step6 = serializers.CharField()
    step7 = serializers.CharField()
    logo = HybridImageField(required=False, allow_null=True)

    def validate(self, data):
        s1 = _parse_step(data['step1'], 'step1')
        s2 = _parse_step(data['step2'], 'step2')
        s3 = _parse_step(data['step3'], 'step3')
        s4 = _parse_step(data['step4'], 'step4')
        s5 = _parse_step(data['step5'], 'step5')
        s6 = _parse_step(data['step6'], 'step6')
        s7 = _parse_step(data['step7'], 'step7')

        if not s1.get('name', '').strip():
            raise serializers.ValidationError({'step1': {'name': 'Название клиники обязательно'}})

        email = s2.get('email', '')
        if not email:
            raise serializers.ValidationError({'step2': {'email': 'Email обязателен'}})
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({'step2': {'email': 'Пользователь с таким email уже существует'}})

        if not s7.get('agree_terms'):
            raise serializers.ValidationError({'step7': 'Необходимо принять условия использования'})
        if not s7.get('agree_privacy'):
            raise serializers.ValidationError({'step7': 'Необходимо принять политику конфиденциальности'})
        if not s7.get('agree_data_processing'):
            raise serializers.ValidationError({'step7': 'Необходимо дать согласие на обработку данных'})
        if not s7.get('agree_publishing'):
            raise serializers.ValidationError({'step7': 'Необходимо дать согласие на публикацию'})

        data['_s1'] = s1
        data['_s2'] = s2
        data['_s3'] = s3
        data['_s4'] = s4
        data['_s5'] = s5
        data['_s6'] = s6
        data['_s7'] = s7
        return data

    def create(self, validated_data):
        from django.db import transaction

        s1 = validated_data['_s1']
        s2 = validated_data['_s2']
        s3 = validated_data['_s3']
        s4 = validated_data['_s4']
        s5 = validated_data['_s5']
        s6 = validated_data['_s6']
        s7 = validated_data['_s7']

        location = s2.get('location') or {}

        with transaction.atomic():
            user = User.objects.create_user(
                email=s2['email'],
                password=validated_data['password'],
                first_name=s1['name'],
                last_name='',
                phone=s2.get('phone', ''),
                role=User.Role.CLINIC,
            )

            ClinicProfile.objects.create(
                user=user,
                # Step 1
                name=s1['name'],
                clinic_type=s1.get('type', ''),
                description=s1.get('description', ''),
                logo=validated_data.get('logo'),
                # Step 2
                country=s2.get('country', ''),
                city=s2.get('city', ''),
                address=s2.get('address', ''),
                phone=s2.get('phone', ''),
                email=s2.get('email', ''),
                website=s2.get('website', ''),
                latitude=location.get('lat'),
                longitude=location.get('lng'),
                # Step 3
                schedule=s3.get('schedule', {}),
                lunch_break=s3.get('lunch_break', {}),
                emergency_24_7=s3.get('emergency_24_7', False),
                # Step 4
                legal_name=s4.get('legal_name', ''),
                reg_number=s4.get('reg_number', ''),
                license_number=s4.get('license_number', ''),
                license_date=s4.get('license_date') or None,
                license_authority=s4.get('license_authority', ''),
                # Step 5
                primary_specializations=s5.get('primary_specializations', []),
                narrow_specializations=s5.get('narrow_specializations', []),
                additional_services=s5.get('additional_services', ''),
                # Step 6
                equipment=s6.get('equipment', []),
                patient_conditions=s6.get('patient_conditions', []),
                payment_methods=s6.get('payment_methods', []),
                # Step 7
                agree_terms=s7.get('agree_terms', False),
                agree_privacy=s7.get('agree_privacy', False),
                agree_data_processing=s7.get('agree_data_processing', False),
                agree_publishing=s7.get('agree_publishing', False),
            )

        return user
