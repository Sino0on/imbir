"""
Команда для заполнения базы данных тестовыми данными.

Использование:
    python manage.py seed_data          # создать данные
    python manage.py seed_data --flush  # удалить все данные и пересоздать
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date, time, timedelta
import random

from users.models import (
    User, DoctorProfile, PatientProfile,
    ClinicProfile, ClinicBranch, ClinicInvite, DoctorClinicLink,
)
from services.models import Service
from appointments.models import Appointment
from reviews.models import Review


DOCTOR_PASSWORD = "Test1234!"
PATIENT_PASSWORD = "Test1234!"
CLINIC_PASSWORD = "Test1234!"
ADMIN_PASSWORD = "admin123"


class Command(BaseCommand):
    help = "Заполнить базу данных тестовыми данными"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Удалить все существующие данные перед созданием",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        with transaction.atomic():
            admin = self._create_admin()
            patients = self._create_patients()
            doctors, doctor_profiles = self._create_doctors()
            clinics, clinic_profiles = self._create_clinics()
            branches = self._create_branches(clinic_profiles)
            self._link_doctors_to_clinics(doctor_profiles, clinic_profiles, branches)
            services = self._create_services(clinic_profiles, doctor_profiles)
            appointments = self._create_appointments(patients, doctor_profiles, clinic_profiles, services)
            self._create_reviews(patients, doctor_profiles, clinic_profiles, appointments)

        self.stdout.write(self.style.SUCCESS("\n✓ Тестовые данные успешно созданы!\n"))
        self.stdout.write("Учётные записи:")
        self.stdout.write(f"  Администратор: admin@imbir.kg / {ADMIN_PASSWORD}")
        self.stdout.write(f"  Пациенты:      patient1-3@imbir.kg / {PATIENT_PASSWORD}")
        self.stdout.write(f"  Врачи:         doctor1-3@imbir.kg / {DOCTOR_PASSWORD}")
        self.stdout.write(f"  Клиники:       clinic1-2@imbir.kg / {CLINIC_PASSWORD}")

    # ------------------------------------------------------------------
    def _flush(self):
        self.stdout.write("Удаление существующих данных...")
        Review.objects.all().delete()
        Appointment.objects.all().delete()
        Service.objects.all().delete()
        DoctorClinicLink.objects.all().delete()
        ClinicInvite.objects.all().delete()
        ClinicBranch.objects.all().delete()
        DoctorProfile.objects.all().delete()
        PatientProfile.objects.all().delete()
        ClinicProfile.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        User.objects.filter(email="admin@imbir.kg").delete()
        self.stdout.write(self.style.WARNING("  Данные удалены."))

    # ------------------------------------------------------------------
    def _create_admin(self):
        user, created = User.objects.get_or_create(
            email="admin@imbir.kg",
            defaults={
                "first_name": "Администратор",
                "last_name": "Imbir",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_password(ADMIN_PASSWORD)
            user.save()
            self.stdout.write("  Создан администратор")
        return user

    # ------------------------------------------------------------------
    def _create_patients(self):
        data = [
            ("Айгерим", "Асанова", "patient1@imbir.kg", "+996700111001"),
            ("Бекзат",  "Омуров",  "patient2@imbir.kg", "+996700111002"),
            ("Чынара",  "Кадырова","patient3@imbir.kg", "+996700111003"),
        ]
        users = []
        for first_name, last_name, email, phone in data:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                    "role": User.Role.PATIENT,
                },
            )
            if created:
                user.set_password(PATIENT_PASSWORD)
                user.save()
            PatientProfile.objects.get_or_create(
                user=user,
                defaults={
                    "blood_type": random.choice(["A+", "B+", "O+", "AB+"]),
                    "allergies": [],
                    "emergency_contact_name": "Экстренный контакт",
                    "emergency_contact_phone": "+996700000000",
                    "emergency_contact_relation": "Родственник",
                },
            )
            users.append(user)
        self.stdout.write(f"  Создано пациентов: {len(users)}")
        return users

    # ------------------------------------------------------------------
    def _create_doctors(self):
        data = [
            {
                "email": "doctor1@imbir.kg",
                "first_name": "Айдар",
                "last_name": "Маматов",
                "phone": "+996700222001",
                "profile": {
                    "gender": "male",
                    "birth_date": date(1985, 3, 15),
                    "city": "Бишкек",
                    "languages": ["ru", "ky"],
                    "country": "Кыргызстан",
                    "address": "ул. Токтогула 100",
                    "primary_specializations": ["Терапевт"],
                    "narrow_specializations": ["Общая терапия", "Гастроэнтерология"],
                    "about": "Опытный терапевт с более чем 10-летним стажем. Специализируюсь на диагностике и лечении заболеваний внутренних органов.",
                    "experience_years": 10,
                    "is_online_available": True,
                    "consultation_price": 800,
                    "education": [
                        {"institution": "КРСУ им. Ельцина", "degree": "Высшее медицинское", "year": 2008},
                        {"institution": "ординатура КГМУ", "degree": "Специализация «Терапия»", "year": 2010},
                    ],
                    "work_experience": [
                        {"clinic": "ГКБ №1", "position": "Терапевт", "from": 2010, "to": 2018},
                        {"clinic": "МЦ Ак-Жол", "position": "Ведущий терапевт", "from": 2018, "to": None},
                    ],
                    "skills": ["Диагностика", "ЭКГ", "УЗИ", "ФГДС"],
                    "equipment": ["ЭКГ-аппарат", "Тонометр"],
                    "payment_methods": ["cash", "card"],
                    "patient_conditions": ["adults", "seniors"],
                    "schedule": {
                        "mon": {"start": "09:00", "end": "18:00"},
                        "tue": {"start": "09:00", "end": "18:00"},
                        "wed": {"start": "09:00", "end": "18:00"},
                        "thu": {"start": "09:00", "end": "18:00"},
                        "fri": {"start": "09:00", "end": "16:00"},
                    },
                    "lunch_break": {"start": "13:00", "end": "14:00"},
                    "rating": 4.8,
                    "reviews_count": 42,
                    "is_published": True,
                    "agree_terms": True,
                    "agree_privacy": True,
                    "agree_data_processing": True,
                    "agree_publishing": True,
                },
            },
            {
                "email": "doctor2@imbir.kg",
                "first_name": "Нурила",
                "last_name": "Сейткалиева",
                "phone": "+996700222002",
                "profile": {
                    "gender": "female",
                    "birth_date": date(1988, 7, 22),
                    "city": "Бишкек",
                    "languages": ["ru", "ky", "en"],
                    "country": "Кыргызстан",
                    "address": "пр. Манаса 55",
                    "primary_specializations": ["Кардиолог"],
                    "narrow_specializations": ["Аритмология", "Эхокардиография"],
                    "about": "Кардиолог высшей категории. Специализируюсь на диагностике и лечении заболеваний сердечно-сосудистой системы.",
                    "experience_years": 8,
                    "is_online_available": True,
                    "consultation_price": 1200,
                    "education": [
                        {"institution": "КГМУ", "degree": "Высшее медицинское", "year": 2011},
                        {"institution": "НЦКиТ", "degree": "Клиническая кардиология", "year": 2013},
                    ],
                    "work_experience": [
                        {"clinic": "НЦКиТ", "position": "Кардиолог", "from": 2013, "to": 2020},
                        {"clinic": "Клиника Здоровье", "position": "Ведущий кардиолог", "from": 2020, "to": None},
                    ],
                    "skills": ["ЭКГ", "Эхокардиография", "Холтеровское мониторирование", "Стресс-тест"],
                    "equipment": ["ЭКГ-аппарат", "Эхокардиограф", "Холтер-монитор"],
                    "payment_methods": ["cash", "card", "insurance"],
                    "patient_conditions": ["adults", "seniors"],
                    "schedule": {
                        "mon": {"start": "08:00", "end": "17:00"},
                        "tue": {"start": "08:00", "end": "17:00"},
                        "wed": {"start": "08:00", "end": "17:00"},
                        "thu": {"start": "08:00", "end": "17:00"},
                        "fri": {"start": "08:00", "end": "15:00"},
                        "sat": {"start": "09:00", "end": "13:00"},
                    },
                    "lunch_break": {"start": "12:00", "end": "13:00"},
                    "rating": 4.9,
                    "reviews_count": 67,
                    "is_published": True,
                    "agree_terms": True,
                    "agree_privacy": True,
                    "agree_data_processing": True,
                    "agree_publishing": True,
                },
            },
            {
                "email": "doctor3@imbir.kg",
                "first_name": "Бакыт",
                "last_name": "Токтоматов",
                "phone": "+996700222003",
                "profile": {
                    "gender": "male",
                    "birth_date": date(1990, 11, 5),
                    "city": "Бишкек",
                    "languages": ["ru", "ky"],
                    "country": "Кыргызстан",
                    "address": "ул. Ахунбаева 92а",
                    "primary_specializations": ["Педиатр"],
                    "narrow_specializations": ["Неонатология", "Детская аллергология"],
                    "about": "Педиатр с 6-летним опытом. Специализируюсь на диагностике и лечении детских заболеваний, аллергических реакций.",
                    "experience_years": 6,
                    "is_online_available": False,
                    "consultation_price": 700,
                    "education": [
                        {"institution": "КРСУ им. Ельцина", "degree": "Высшее медицинское (педиатрия)", "year": 2014},
                        {"institution": "ординатура КГМУ", "degree": "Педиатрия", "year": 2016},
                    ],
                    "work_experience": [
                        {"clinic": "Детская ГКБ №2", "position": "Педиатр", "from": 2016, "to": 2022},
                        {"clinic": "МЦ Ак-Жол", "position": "Педиатр", "from": 2022, "to": None},
                    ],
                    "skills": ["Педиатрия", "Вакцинация", "Аллергология", "Неонатология"],
                    "equipment": ["Тонометр детский", "Пульсоксиметр"],
                    "payment_methods": ["cash", "card"],
                    "patient_conditions": ["children", "infants"],
                    "schedule": {
                        "mon": {"start": "09:00", "end": "18:00"},
                        "tue": {"start": "09:00", "end": "18:00"},
                        "wed": {"start": "09:00", "end": "18:00"},
                        "thu": {"start": "09:00", "end": "18:00"},
                        "fri": {"start": "09:00", "end": "16:00"},
                    },
                    "lunch_break": {"start": "13:00", "end": "14:00"},
                    "rating": 4.7,
                    "reviews_count": 28,
                    "is_published": True,
                    "agree_terms": True,
                    "agree_privacy": True,
                    "agree_data_processing": True,
                    "agree_publishing": True,
                },
            },
        ]

        users, profiles = [], []
        for item in data:
            user, created = User.objects.get_or_create(
                email=item["email"],
                defaults={
                    "first_name": item["first_name"],
                    "last_name": item["last_name"],
                    "phone": item["phone"],
                    "role": User.Role.DOCTOR,
                },
            )
            if created:
                user.set_password(DOCTOR_PASSWORD)
                user.save()

            profile, _ = DoctorProfile.objects.get_or_create(user=user, defaults=item["profile"])
            users.append(user)
            profiles.append(profile)

        self.stdout.write(f"  Создано врачей: {len(users)}")
        return users, profiles

    # ------------------------------------------------------------------
    def _create_clinics(self):
        data = [
            {
                "email": "clinic1@imbir.kg",
                "first_name": "МЦ",
                "last_name": "Ак-Жол",
                "phone": "+996312123401",
                "profile": {
                    "name": "Медицинский центр «Ак-Жол»",
                    "clinic_type": "Многопрофильная клиника",
                    "description": "Многопрофильный медицинский центр в Бишкеке с современным оборудованием и опытными специалистами. Предоставляем полный спектр медицинских услуг.",
                    "country": "Кыргызстан",
                    "city": "Бишкек",
                    "address": "ул. Токтогула 100",
                    "phone": "+996312123401",
                    "email": "info@akzhol.kg",
                    "website": "https://akzhol.kg",
                    "latitude": 42.8701,
                    "longitude": 74.5901,
                    "primary_specializations": ["Терапия", "Педиатрия", "Хирургия"],
                    "narrow_specializations": ["Гастроэнтерология", "Неврология"],
                    "additional_services": "Лаборатория, рентген, УЗИ, ЭКГ",
                    "equipment": ["МРТ", "КТ", "УЗИ", "Рентген", "Лаборатория"],
                    "patient_conditions": ["adults", "children", "seniors"],
                    "payment_methods": ["cash", "card", "insurance"],
                    "schedule": {
                        "mon": {"start": "08:00", "end": "20:00"},
                        "tue": {"start": "08:00", "end": "20:00"},
                        "wed": {"start": "08:00", "end": "20:00"},
                        "thu": {"start": "08:00", "end": "20:00"},
                        "fri": {"start": "08:00", "end": "20:00"},
                        "sat": {"start": "09:00", "end": "17:00"},
                        "sun": {"start": "09:00", "end": "14:00"},
                    },
                    "lunch_break": {},
                    "experience_years": 15,
                    "rating": 4.7,
                    "reviews_count": 214,
                    "doctors_count": 25,
                    "is_published": True,
                    "legal_name": "ОсОО «Ак-Жол Мед»",
                    "reg_number": "12345-6789",
                    "license_number": "МЦ-001-2010",
                    "license_date": date(2010, 6, 1),
                    "license_authority": "Министерство здравоохранения КР",
                    "agree_terms": True,
                    "agree_privacy": True,
                    "agree_data_processing": True,
                    "agree_publishing": True,
                },
            },
            {
                "email": "clinic2@imbir.kg",
                "first_name": "Клиника",
                "last_name": "Здоровье",
                "phone": "+996312456702",
                "profile": {
                    "name": "Клиника «Здоровье»",
                    "clinic_type": "Кардиологическая клиника",
                    "description": "Специализированная кардиологическая клиника. Диагностика и лечение сердечно-сосудистых заболеваний с применением современных технологий.",
                    "country": "Кыргызстан",
                    "city": "Бишкек",
                    "address": "пр. Манаса 55",
                    "phone": "+996312456702",
                    "email": "info@zdorovie.kg",
                    "website": "https://zdorovie.kg",
                    "latitude": 42.8750,
                    "longitude": 74.6100,
                    "primary_specializations": ["Кардиология"],
                    "narrow_specializations": ["Аритмология", "Интервенционная кардиология"],
                    "additional_services": "Кардиохирургия, реабилитация",
                    "equipment": ["ЭКГ", "Эхокардиограф", "Холтер", "Ангиограф"],
                    "patient_conditions": ["adults", "seniors"],
                    "payment_methods": ["cash", "card", "insurance"],
                    "schedule": {
                        "mon": {"start": "08:00", "end": "19:00"},
                        "tue": {"start": "08:00", "end": "19:00"},
                        "wed": {"start": "08:00", "end": "19:00"},
                        "thu": {"start": "08:00", "end": "19:00"},
                        "fri": {"start": "08:00", "end": "19:00"},
                        "sat": {"start": "09:00", "end": "15:00"},
                    },
                    "lunch_break": {"start": "13:00", "end": "14:00"},
                    "experience_years": 10,
                    "rating": 4.9,
                    "reviews_count": 189,
                    "doctors_count": 12,
                    "is_published": True,
                    "legal_name": "ОсОО «Здоровье»",
                    "reg_number": "98765-4321",
                    "license_number": "КК-002-2015",
                    "license_date": date(2015, 3, 20),
                    "license_authority": "Министерство здравоохранения КР",
                    "agree_terms": True,
                    "agree_privacy": True,
                    "agree_data_processing": True,
                    "agree_publishing": True,
                },
            },
        ]

        users, profiles = [], []
        for item in data:
            user, created = User.objects.get_or_create(
                email=item["email"],
                defaults={
                    "first_name": item["first_name"],
                    "last_name": item["last_name"],
                    "phone": item["phone"],
                    "role": User.Role.CLINIC,
                },
            )
            if created:
                user.set_password(CLINIC_PASSWORD)
                user.save()

            profile, _ = ClinicProfile.objects.get_or_create(user=user, defaults=item["profile"])
            users.append(user)
            profiles.append(profile)

        self.stdout.write(f"  Создано клиник: {len(users)}")
        return users, profiles

    # ------------------------------------------------------------------
    def _create_branches(self, clinic_profiles):
        branches_data = [
            # Ак-Жол — 2 филиала
            (clinic_profiles[0], "Главный офис", "ул. Токтогула 100", "+996312123401"),
            (clinic_profiles[0], "Филиал Южный", "мкр. Асанбай 12", "+996312123402"),
            # Здоровье — 1 филиал
            (clinic_profiles[1], "Главный офис", "пр. Манаса 55", "+996312456702"),
        ]
        branches = []
        for clinic, name, address, phone in branches_data:
            branch, _ = ClinicBranch.objects.get_or_create(
                clinic=clinic,
                name=name,
                defaults={
                    "address": address,
                    "phone": phone,
                    "schedule": {
                        "mon": {"start": "08:00", "end": "20:00"},
                        "fri": {"start": "08:00", "end": "18:00"},
                    },
                },
            )
            branches.append(branch)
        self.stdout.write(f"  Создано филиалов: {len(branches)}")
        return branches

    # ------------------------------------------------------------------
    def _link_doctors_to_clinics(self, doctor_profiles, clinic_profiles, branches):
        links = [
            # doctor1 (Маматов) — Ак-Жол, главный офис
            (doctor_profiles[0], clinic_profiles[0], branches[0]),
            # doctor3 (Токтоматов) — Ак-Жол, главный офис
            (doctor_profiles[2], clinic_profiles[0], branches[0]),
            # doctor2 (Сейткалиева) — Здоровье
            (doctor_profiles[1], clinic_profiles[1], branches[2]),
        ]
        for doctor, clinic, branch in links:
            DoctorClinicLink.objects.get_or_create(
                doctor=doctor,
                clinic=clinic,
                defaults={"branch": branch, "is_active": True},
            )
        self.stdout.write(f"  Создано связей врач-клиника: {len(links)}")

    # ------------------------------------------------------------------
    def _create_services(self, clinic_profiles, doctor_profiles):
        data = [
            # Ак-Жол услуги
            ("Терапия", "Первичная консультация терапевта", 800, 30, clinic_profiles[0], doctor_profiles[0]),
            ("Терапия", "Повторная консультация терапевта", 500, 20, clinic_profiles[0], doctor_profiles[0]),
            ("Педиатрия", "Консультация педиатра", 700, 30, clinic_profiles[0], doctor_profiles[2]),
            ("Педиатрия", "Профилактический осмотр ребёнка", 600, 40, clinic_profiles[0], doctor_profiles[2]),
            ("Лаборатория", "Общий анализ крови", 400, 5, clinic_profiles[0], None),
            ("Лаборатория", "Биохимический анализ крови", 800, 5, clinic_profiles[0], None),
            ("Диагностика", "УЗИ органов брюшной полости", 1200, 30, clinic_profiles[0], None),
            ("Диагностика", "ЭКГ", 600, 15, clinic_profiles[0], None),
            # Здоровье услуги
            ("Кардиология", "Консультация кардиолога", 1200, 45, clinic_profiles[1], doctor_profiles[1]),
            ("Кардиология", "Эхокардиография (ЭхоКГ)", 2500, 60, clinic_profiles[1], doctor_profiles[1]),
            ("Кардиология", "Холтеровское мониторирование ЭКГ", 3000, None, clinic_profiles[1], doctor_profiles[1]),
            ("Диагностика", "Суточное мониторирование АД", 2000, None, clinic_profiles[1], None),
        ]
        services = []
        for category, name, price, duration, clinic, doctor in data:
            service, _ = Service.objects.get_or_create(
                name=name,
                clinic=clinic,
                defaults={
                    "category": category,
                    "price": price,
                    "duration": duration,
                    "doctor": doctor,
                    "is_active": True,
                },
            )
            services.append(service)
        self.stdout.write(f"  Создано услуг: {len(services)}")
        return services

    # ------------------------------------------------------------------
    def _create_appointments(self, patients, doctor_profiles, clinic_profiles, services):
        today = date.today()
        data = [
            {
                "patient": patients[0],
                "doctor": doctor_profiles[0],
                "clinic": clinic_profiles[0],
                "service": services[0],
                "date": today - timedelta(days=10),
                "time": time(10, 0),
                "is_online": False,
                "status": Appointment.Status.COMPLETED,
                "notes": "Жалобы на боли в животе",
            },
            {
                "patient": patients[1],
                "doctor": doctor_profiles[1],
                "clinic": clinic_profiles[1],
                "service": services[8],
                "date": today - timedelta(days=5),
                "time": time(14, 30),
                "is_online": False,
                "status": Appointment.Status.COMPLETED,
                "notes": "Плановый осмотр, аритмия",
            },
            {
                "patient": patients[2],
                "doctor": doctor_profiles[2],
                "clinic": clinic_profiles[0],
                "service": services[2],
                "date": today + timedelta(days=2),
                "time": time(11, 0),
                "is_online": False,
                "status": Appointment.Status.CONFIRMED,
                "notes": "",
            },
            {
                "patient": patients[0],
                "doctor": doctor_profiles[0],
                "clinic": clinic_profiles[0],
                "service": services[1],
                "date": today + timedelta(days=7),
                "time": time(9, 30),
                "is_online": True,
                "status": Appointment.Status.PENDING,
                "notes": "Онлайн-консультация",
            },
            {
                "patient": None,
                "guest_name": "Марат Байсалов",
                "guest_phone": "+996700555999",
                "guest_email": "marat@example.com",
                "doctor": doctor_profiles[1],
                "clinic": clinic_profiles[1],
                "service": services[8],
                "date": today + timedelta(days=3),
                "time": time(16, 0),
                "is_online": False,
                "status": Appointment.Status.PENDING,
                "notes": "Гостевая запись",
            },
            {
                "patient": patients[1],
                "doctor": doctor_profiles[0],
                "clinic": clinic_profiles[0],
                "service": services[0],
                "date": today - timedelta(days=20),
                "time": time(15, 0),
                "is_online": False,
                "status": Appointment.Status.CANCELLED,
                "notes": "Пациент отменил запись",
            },
        ]
        appointments = []
        for item in data:
            guest_name = item.pop("guest_name", "")
            guest_phone = item.pop("guest_phone", "")
            guest_email = item.pop("guest_email", "")
            appt, _ = Appointment.objects.get_or_create(
                patient=item["patient"],
                doctor=item["doctor"],
                date=item["date"],
                time=item["time"],
                defaults={**item, "guest_name": guest_name, "guest_phone": guest_phone, "guest_email": guest_email},
            )
            appointments.append(appt)
        self.stdout.write(f"  Создано записей на приём: {len(appointments)}")
        return appointments

    # ------------------------------------------------------------------
    def _create_reviews(self, patients, doctor_profiles, clinic_profiles, appointments):
        completed = [a for a in appointments if a.status == Appointment.Status.COMPLETED]
        data = [
            {
                "author": patients[0],
                "appointment": completed[0] if len(completed) > 0 else None,
                "target_type": Review.TargetType.DOCTOR,
                "doctor": doctor_profiles[0],
                "clinic": None,
                "rating": 5,
                "text": "Отличный врач! Айдар очень внимательно выслушал, поставил правильный диагноз. Рекомендую всем!",
            },
            {
                "author": patients[1],
                "appointment": completed[1] if len(completed) > 1 else None,
                "target_type": Review.TargetType.DOCTOR,
                "doctor": doctor_profiles[1],
                "clinic": None,
                "rating": 5,
                "text": "Нурила — профессионал высшего класса. Очень компетентна, объяснила всё понятно. Очень довольна приёмом.",
            },
            {
                "author": patients[0],
                "appointment": None,
                "target_type": Review.TargetType.CLINIC,
                "doctor": None,
                "clinic": clinic_profiles[0],
                "rating": 4,
                "text": "Хорошая клиника, современное оборудование. Единственный минус — долгое ожидание в очереди.",
            },
            {
                "author": patients[1],
                "appointment": None,
                "target_type": Review.TargetType.CLINIC,
                "doctor": None,
                "clinic": clinic_profiles[1],
                "rating": 5,
                "text": "Лучшая кардиологическая клиника в городе! Отличный персонал, новейшее оборудование, быстрое обслуживание.",
            },
            {
                "author": patients[2],
                "appointment": None,
                "target_type": Review.TargetType.DOCTOR,
                "doctor": doctor_profiles[2],
                "clinic": None,
                "rating": 5,
                "text": "Бакыт замечательный педиатр! Ребёнок его совсем не боится, всегда чувствуем заботу и профессионализм.",
            },
        ]
        count = 0
        for item in data:
            if not Review.objects.filter(author=item["author"], target_type=item["target_type"],
                                         doctor=item.get("doctor"), clinic=item.get("clinic")).exists():
                Review.objects.create(**item)
                count += 1
        self.stdout.write(f"  Создано отзывов: {count}")
