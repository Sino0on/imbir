"""Карточка врача в кабинете клиники: график по умолчанию у созданного клиникой
врача, «О себе», multipart со списками и очисткой полей (K17, K26, K32, N58)."""
import datetime
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from appointments.utils import doctor_lunch_break, doctor_work_hours
from references.models import Specialization
from services.models import Service
from users.models import ClinicProfile, DoctorClinicLink, DoctorProfile, User

DOCTORS_URL = '/api/clinic/doctors/'
PROFILE_URL = '/api/clinic/profile/'


def _png(name='photo.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), (10, 120, 200)).save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def _next_weekday(weekday):
    today = datetime.date.today()
    return today + datetime.timedelta(days=(weekday - today.weekday()) % 7 or 7)


class _ClinicSpecialistsBase(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.clinic_user = User.objects.create_user(
            email='spec-clinic@example.com', password='password123', first_name='Клиника', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Клиника', city='Бишкек', country='Кыргызстан',
        )
        self.therapy = Specialization.objects.create(name='Терапевт')
        self.cardio = Specialization.objects.create(name='Кардиолог')
        self.client.force_authenticate(user=self.clinic_user)

    def _attached_doctor(self, **profile):
        user = User.objects.create_user(
            email='spec-doctor@example.com', password='password123', first_name='Асель', last_name='Иванова',
            role=User.Role.DOCTOR,
        )
        doctor = DoctorProfile.objects.create(user=user, city='Бишкек', is_published=True, **profile)
        DoctorClinicLink.objects.create(doctor=doctor, clinic=self.clinic)
        return doctor


class ClinicCreatedDoctorScheduleTests(_ClinicSpecialistsBase):
    """K17: врач, заведённый клиникой, сразу опубликован — значит, у него должен
    быть рабочий график, иначе свободных слотов нет и любая запись падает."""

    def _create(self, **extra):
        response = self.client.post(DOCTORS_URL, {
            'first_name': 'Алина', 'last_name': 'Садыкова', 'email': 'new-doc@example.com', **extra,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return DoctorProfile.objects.get(user__email='new-doc@example.com')

    def test_default_schedule_is_weekdays_9_to_18(self):
        doctor = self._create()
        monday = _next_weekday(0)
        start, end = doctor_work_hours(doctor, monday)
        self.assertEqual((start.time(), end.time()), (datetime.time(9, 0), datetime.time(18, 0)))
        self.assertIsNone(doctor_work_hours(doctor, _next_weekday(6)))

        response = self.client.get(f'/api/doctors/{doctor.user_id}/available-slots/', {'date': monday.isoformat()})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['slots'])

    def test_clinic_schedule_and_lunch_are_copied(self):
        self.clinic.schedule = {
            'monday': {'enabled': True, 'from': '08:00', 'to': '14:00'},
            'saturday': {'enabled': True, 'from': '10:00', 'to': '15:00'},
            'sunday': {'enabled': False, 'from': None, 'to': None},
        }
        self.clinic.lunch_break = {'from': '12:00', 'to': '13:00'}
        self.clinic.save()

        doctor = self._create()
        start, end = doctor_work_hours(doctor, _next_weekday(0))
        self.assertEqual((start.time(), end.time()), (datetime.time(8, 0), datetime.time(14, 0)))
        self.assertIsNotNone(doctor_work_hours(doctor, _next_weekday(5)))
        self.assertIsNone(doctor_work_hours(doctor, _next_weekday(1)))
        lunch = doctor_lunch_break(doctor, _next_weekday(0))
        self.assertEqual((lunch[0].time(), lunch[1].time()), (datetime.time(12, 0), datetime.time(13, 0)))

    def test_clinic_lunch_in_start_end_format_is_copied(self):
        self.clinic.lunch_break = {'start': '13:00', 'end': '14:00'}
        self.clinic.save()

        doctor = self._create()
        self.assertEqual(doctor.lunch_break, {'from': '13:00', 'to': '14:00'})

    def test_clinic_can_patch_doctor_schedule(self):
        doctor = self._attached_doctor()
        schedule = {'tuesday': {'enabled': True, 'from': '10:00', 'to': '16:00'}}
        response = self.client.patch(
            f'{DOCTORS_URL}{doctor.user_id}/',
            {'schedule': schedule, 'lunch_break': {'from': '13:00', 'to': '14:00'}},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        doctor.refresh_from_db()
        self.assertEqual(doctor.schedule, schedule)
        self.assertEqual(doctor.lunch_break, {'from': '13:00', 'to': '14:00'})
        self.assertEqual(response.data['schedule'], schedule)


class ClinicDoctorAboutTests(_ClinicSpecialistsBase):
    """K32: «О себе» из формы клиники сохраняется и при создании, и при правке."""

    def test_about_saved_on_create(self):
        response = self.client.post(DOCTORS_URL, {
            'first_name': 'Алина', 'last_name': 'Садыкова', 'email': 'about@example.com', 'about': 'Лечу сердце',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(DoctorProfile.objects.get(user__email='about@example.com').about, 'Лечу сердце')

    def test_about_saved_on_patch_and_returned(self):
        doctor = self._attached_doctor()
        response = self.client.patch(f'{DOCTORS_URL}{doctor.user_id}/', {'about': 'Новый текст'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        doctor.refresh_from_db()
        self.assertEqual(doctor.about, 'Новый текст')
        self.assertEqual(self.client.get(f'{DOCTORS_URL}{doctor.user_id}/').data['about'], 'Новый текст')


class ClinicDoctorMultipartTests(_ClinicSpecialistsBase):
    """K26, N58: списки в multipart приходят JSON-строкой, а '[]' и '' очищают поле."""

    def test_create_with_photo_parses_json_lists(self):
        education = [{'institution': 'КГМА', 'degree': 'Лечебное дело', 'year': 2010}]
        response = self.client.post(DOCTORS_URL, {
            'first_name': 'Алина', 'last_name': 'Садыкова', 'email': 'multi@example.com',
            'photo': _png(),
            'languages': '["Русский", "Кыргызский"]',
            'education': '[{"institution": "КГМА", "degree": "Лечебное дело", "year": 2010}]',
            'additional_education': '[{"name": "ЭКГ", "year": 2020}]',
            'primary_specialization_ids': [str(self.therapy.id), str(self.cardio.id)],
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        doctor = DoctorProfile.objects.get(user__email='multi@example.com')
        self.assertEqual(doctor.languages, ['Русский', 'Кыргызский'])
        self.assertEqual(doctor.education, education)
        self.assertEqual(doctor.additional_education, [{'name': 'ЭКГ', 'year': 2020}])
        self.assertEqual(set(doctor.primary_specializations.all()), {self.therapy, self.cardio})
        self.assertTrue(doctor.photo)

    def test_patch_with_photo_clears_lists_and_date(self):
        doctor = self._attached_doctor(languages=['Русский'], birth_date=datetime.date(1980, 1, 1))
        doctor.narrow_specializations.set([self.cardio])
        response = self.client.patch(f'{DOCTORS_URL}{doctor.user_id}/', {
            'photo': _png(),
            'narrow_specialization_ids': '[]',
            'languages': '[]',
            'birth_date': '',
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        doctor.refresh_from_db()
        self.assertEqual(list(doctor.narrow_specializations.all()), [])
        self.assertEqual(doctor.languages, [])
        self.assertIsNone(doctor.birth_date)
        self.assertTrue(doctor.photo)

    def test_patch_with_photo_accepts_json_id_list(self):
        doctor = self._attached_doctor()
        response = self.client.patch(f'{DOCTORS_URL}{doctor.user_id}/', {
            'photo': _png(), 'primary_specialization_ids': f'[{self.therapy.id}, {self.cardio.id}]',
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(doctor.primary_specializations.all()), {self.therapy, self.cardio})

    def test_service_put_with_photo_clears_doctors(self):
        doctor = self._attached_doctor()
        service = Service.objects.create(name='УЗИ', category='diagnostics', clinic=self.clinic)
        doctor.services.add(service)
        response = self.client.put(
            f'/api/clinic/services/{service.id}/', {'photo': _png(), 'doctor_ids': '[]'}, format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(service.doctors.all()), [])

    def test_service_put_repeated_doctor_ids_still_work(self):
        doctor = self._attached_doctor()
        service = Service.objects.create(name='УЗИ', category='diagnostics', clinic=self.clinic)
        response = self.client.put(
            f'/api/clinic/services/{service.id}/',
            {'photo': _png(), 'doctor_ids': [str(doctor.user_id)]}, format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(service.doctors.all()), [doctor])

    def test_clinic_profile_logo_put_clears_specializations_and_lists(self):
        self.clinic.equipment = ['УЗИ']
        self.clinic.save()
        self.clinic.narrow_specializations.set([self.cardio])
        response = self.client.put(PROFILE_URL, {
            'logo': _png('logo.png'), 'narrow_specialization_ids': '[]', 'equipment': '[]', 'license_date': '',
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.clinic.refresh_from_db()
        self.assertEqual(list(self.clinic.narrow_specializations.all()), [])
        self.assertEqual(self.clinic.equipment, [])
        self.assertIsNone(self.clinic.license_date)
