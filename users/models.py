import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        PATIENT = 'patient', 'Пациент'
        DOCTOR = 'doctor', 'Врач'
        CLINIC = 'clinic', 'Клиника'
        ADMIN = 'admin', 'Администратор'

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    patronymic = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='users/avatars/', null=True, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PATIENT)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    favorite_doctors = models.ManyToManyField('users.DoctorProfile', related_name='favorited_by_users', blank=True)
    favorite_clinics = models.ManyToManyField('users.ClinicProfile', related_name='favorited_by_users', blank=True)
    favorite_services = models.ManyToManyField('services.Service', related_name='favorited_by_users', blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f'{self.first_name} {self.last_name} ({self.email})'

    @property
    def full_name(self):
        parts = [self.first_name, self.patronymic or '', self.last_name]
        return ' '.join(p for p in parts if p).strip()


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')

    # Step 1 — основная информация
    gender = models.CharField(max_length=10, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    languages = models.JSONField(default=list)
    photo = models.ImageField(upload_to='doctors/photos/', null=True, blank=True)

    # Step 2 — локация
    country = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Step 3 — расписание
    schedule = models.JSONField(default=dict)
    lunch_break = models.JSONField(default=dict, null=True, blank=True)
    emergency_24_7 = models.BooleanField(default=False)

    # Step 4 — юридические данные
    legal_name = models.CharField(max_length=255, blank=True)
    reg_number = models.CharField(max_length=100, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    license_date = models.DateField(null=True, blank=True)
    license_authority = models.CharField(max_length=255, blank=True)

    # Step 5 — специализация
    primary_specializations = models.JSONField(default=list)
    narrow_specializations = models.JSONField(default=list)
    additional_services = models.TextField(blank=True)

    # Step 6 — оборудование и условия
    equipment = models.JSONField(default=list, null=True, blank=True)
    patient_conditions = models.JSONField(default=list, null=True, blank=True)
    payment_methods = models.JSONField(default=list, null=True, blank=True)

    # Step 7 — согласия
    agree_terms = models.BooleanField(default=False)
    agree_privacy = models.BooleanField(default=False)
    agree_data_processing = models.BooleanField(default=False)
    agree_publishing = models.BooleanField(default=False)

    # Публичные поля каталога
    about = models.TextField(blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    is_online_available = models.BooleanField(default=False)
    consultation_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Биография — заполняется врачом в личном кабинете
    # education: [{"institution": "КГМУ", "degree": "Высшее медицинское", "year": 2005}]
    education = models.JSONField(default=list, null=True, blank=True)
    # work_experience: [{"clinic": "ГКБ №1", "position": "Терапевт", "from": 2005, "to": 2015}]
    work_experience = models.JSONField(default=list, null=True, blank=True)
    # skills: ["Диагностика", "УЗИ"]
    skills = models.JSONField(default=list, null=True, blank=True)

    # Кэшированные поля (обновляются при добавлении отзывов)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    reviews_count = models.PositiveIntegerField(default=0)

    is_published = models.BooleanField(default=True)
    profile_views = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)
    services = models.ManyToManyField('services.Service', related_name='doctors', blank=True)

    class Meta:
        verbose_name = 'Профиль врача'
        verbose_name_plural = 'Профили врачей'

    def __str__(self):
        return f'Профиль врача: {self.user.full_name}'


class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')

    blood_type = models.CharField(max_length=10, blank=True)
    allergies = models.JSONField(default=list)

    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    emergency_contact_relation = models.CharField(max_length=100, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Профиль пациента'
        verbose_name_plural = 'Профили пациентов'

    def __str__(self):
        return f'Профиль пациента: {self.user.full_name}'


class DoctorDocument(models.Model):
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='doctors/documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Документ врача'
        verbose_name_plural = 'Документы врача'


class ClinicProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='clinic_profile')

    # Step 1 — основная информация
    name = models.CharField(max_length=255)
    clinic_type = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='clinics/logos/', null=True, blank=True)

    # Step 2 — контакты и локация
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Step 3 — расписание
    schedule = models.JSONField(default=dict)
    lunch_break = models.JSONField(default=dict)
    emergency_24_7 = models.BooleanField(default=False)

    # Step 4 — юридические данные
    legal_name = models.CharField(max_length=255, blank=True)
    reg_number = models.CharField(max_length=100, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    license_date = models.DateField(null=True, blank=True)
    license_authority = models.CharField(max_length=255, blank=True)

    # Step 5 — специализации
    primary_specializations = models.JSONField(default=list)
    narrow_specializations = models.JSONField(default=list)
    additional_services = models.TextField(blank=True)

    # Step 6 — оборудование и условия
    equipment = models.JSONField(default=list)
    patient_conditions = models.JSONField(default=list)
    payment_methods = models.JSONField(default=list)

    # Step 7 — согласия
    agree_terms = models.BooleanField(default=False)
    agree_privacy = models.BooleanField(default=False)
    agree_data_processing = models.BooleanField(default=False)
    agree_publishing = models.BooleanField(default=False)

    # Каталог (кэшированные поля)
    experience_years = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    reviews_count = models.PositiveIntegerField(default=0)
    doctors_count = models.PositiveIntegerField(default=0)

    is_published = models.BooleanField(default=True)
    profile_views = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Профиль клиники'
        verbose_name_plural = 'Профили клиник'

    def __str__(self):
        return self.name


class ClinicPhoto(models.Model):
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='clinics/photos/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Фото клиники'
        verbose_name_plural = 'Фото клиник'


class ClinicDocument(models.Model):
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='clinics/documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Документ клиники'
        verbose_name_plural = 'Документы клиник'



class ClinicBranch(models.Model):
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    schedule = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Филиал клиники'
        verbose_name_plural = 'Филиалы клиник'

    def __str__(self):
        return f'{self.clinic.name} — {self.address}'


class ClinicInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='invites')
    branch = models.ForeignKey(ClinicBranch, on_delete=models.SET_NULL, null=True, blank=True, related_name='invites')
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Инвайт клиники'
        verbose_name_plural = 'Инвайты клиник'

    def __str__(self):
        return f'Инвайт {self.id} ({self.clinic.name})'

    @property
    def is_valid(self):
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class DoctorClinicLink(models.Model):
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='clinic_links')
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='doctor_links')
    branch = models.ForeignKey(ClinicBranch, on_delete=models.SET_NULL, null=True, blank=True, related_name='doctor_links')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Связь врача с клиникой'
        verbose_name_plural = 'Связи врачей с клиниками'
        unique_together = [('doctor', 'clinic')]

    def __str__(self):
        return f'{self.doctor.user.full_name} @ {self.clinic.name}'


class PasswordResetCode(models.Model):
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Код сброса пароля'
        verbose_name_plural = 'Коды сброса пароля'

    def __str__(self):
        identity = self.email or self.phone or 'unknown'
        return f'{identity} -> {self.code}'

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=15)


class PhoneVerificationCode(models.Model):
    phone = models.CharField(max_length=20)
    code = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Код подтверждения телефона'
        verbose_name_plural = 'Коды подтверждения телефонов'

    def __str__(self):
        return f'{self.phone} -> {self.code}'

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)


