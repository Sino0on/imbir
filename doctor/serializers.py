from rest_framework import serializers
from appointments.models import Appointment
from reviews.models import Review
from services.models import Service
from references.models import Specialization
from references.serializers import SpecializationSerializer
from users.models import DoctorInvitation, DoctorProfile, User
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
    clinic = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            'id', 'name', 'category', 'description', 'price', 'duration', 'photo',
            'clinic', 'branch', 'schedule', 'lunch_break', 'is_active', 'created_at',
        )

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url

    def get_clinic(self, obj):
        if not obj.clinic:
            return None
        return {'id': obj.clinic.user_id, 'name': obj.clinic.name}

    def get_branch(self, obj):
        if not obj.branch:
            return None
        return {'id': obj.branch.id, 'name': obj.branch.name, 'address': obj.branch.address}


class DoctorServiceWriteSerializer(serializers.ModelSerializer):
    photo = HybridImageField(required=False, allow_null=True)
    # Явный default: BooleanField в multipart/form-data трактует отсутствие поля как
    # "чекбокс не отмечен" -> False, а не как "использовать default модели" (True).
    # Актуально именно тут, т.к. photo делает multipart нормой, а не исключением.
    is_active = serializers.BooleanField(required=False, default=True)
    # Врач сам эти поля не вводит в обычном случае — берём из его привязок к
    # клинике(-ам). Нужны только если врач состоит в нескольких клиниках сразу.
    clinic_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Service
        fields = (
            'name', 'category', 'description', 'price', 'duration', 'photo',
            'schedule', 'lunch_break', 'is_active', 'clinic_id', 'branch_id',
        )

    @staticmethod
    def _resolve_branch(clinic, link_branch, branch_id):
        """Единая логика для обоих путей (авто-подстановка и явный clinic_id):
        явный branch_id > филиал из привязки врача к этой клинике > если у
        клиники всего один филиал вообще — берём его, неоднозначности нет."""
        from users.models import ClinicBranch

        if branch_id is not None:
            try:
                return ClinicBranch.objects.get(pk=branch_id, clinic=clinic)
            except ClinicBranch.DoesNotExist:
                raise serializers.ValidationError(
                    {'branch_id': 'Этот филиал не принадлежит выбранной клинике.'}
                )

        if link_branch is not None:
            return link_branch

        clinic_branches = list(ClinicBranch.objects.filter(clinic=clinic)[:2])
        if len(clinic_branches) == 1:
            return clinic_branches[0]
        return None

    def validate(self, attrs):
        doctor = self.context['doctor']
        clinic_id = attrs.pop('clinic_id', None)
        branch_id = attrs.pop('branch_id', None)

        # На обновлении трогаем clinic/branch только если явно прислали clinic_id —
        # обычная правка (цена, фото и т.п.) не должна их переопределять.
        if self.instance is not None and clinic_id is None:
            return attrs

        links = list(
            doctor.clinic_links.filter(is_active=True).select_related('clinic', 'branch')
        )

        if not links:
            if clinic_id:
                raise serializers.ValidationError(
                    {'clinic_id': 'Вы не привязаны ни к одной клинике.'}
                )
            if self.instance is None:
                attrs['clinic'] = None
                attrs['branch'] = None
            return attrs

        if clinic_id is None:
            if len(links) > 1:
                raise serializers.ValidationError(
                    {'clinic_id': 'Вы привязаны к нескольким клиникам — укажите clinic_id.'}
                )
            link = links[0]
            attrs['clinic'] = link.clinic
            attrs['branch'] = self._resolve_branch(link.clinic, link.branch, branch_id)
            return attrs

        # clinic_id от клиента — публичный id клиники (= ClinicProfile.user_id,
        # как везде в API), а не ClinicProfile.pk — их нельзя сравнивать напрямую.
        matching_link = next((l for l in links if l.clinic.user_id == clinic_id), None)
        if not matching_link:
            raise serializers.ValidationError({'clinic_id': 'Вы не привязаны к этой клинике.'})
        attrs['clinic'] = matching_link.clinic
        attrs['branch'] = self._resolve_branch(matching_link.clinic, matching_link.branch, branch_id)

        return attrs

    def create(self, validated_data):
        doctor = self.context['doctor']
        service = Service.objects.create(**validated_data)
        doctor.services.add(service)
        return service


class DoctorInvitationSerializer(serializers.ModelSerializer):
    """Приглашения, полученные врачом — с точки зрения врача (какая клиника позвала)."""
    clinic_id = serializers.IntegerField(source='clinic.user_id', read_only=True)
    clinic_name = serializers.CharField(source='clinic.name', read_only=True)
    clinic_logo = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()

    class Meta:
        model = DoctorInvitation
        fields = (
            'id', 'clinic_id', 'clinic_name', 'clinic_logo',
            'branch', 'message', 'status', 'created_at', 'responded_at',
        )

    def get_clinic_logo(self, obj):
        if not obj.clinic.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.clinic.logo.url) if request else obj.clinic.logo.url

    def get_branch(self, obj):
        if not obj.branch:
            return None
        return {'id': obj.branch.id, 'name': obj.branch.name, 'address': obj.branch.address}
