"""N47: врач вписывает в кабинете номер, уже привязанный к другому аккаунту.
Раньше user.save() падал с IntegrityError и бэк отвечал 500."""
from rest_framework.test import APITestCase

from appointments.models import Appointment
from users.models import DoctorProfile, User

URL = '/api/doctor/profile/'


class DoctorProfilePhoneUniqueTests(APITestCase):
    def setUp(self):
        User.objects.create_user(
            email='taken@example.com', password='password123',
            first_name='T', last_name='K', phone='+996700111222',
        )
        self.user = User.objects.create_user(
            email='doc-phone@example.com', password='password123',
            first_name='Алина', last_name='Садыкова', role=User.Role.DOCTOR,
            phone='+996700999000',
        )
        self.profile = DoctorProfile.objects.create(user=self.user)
        self.client.force_authenticate(self.user)

    def test_taken_phone_returns_400(self):
        response = self.client.put(URL, {'phone': '+996700111222'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            str(response.data['phone'][0]),
            'Пользователь с таким номером телефона уже зарегистрирован',
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '+996700999000')

    def test_own_and_new_phone_saved(self):
        self.assertEqual(self.client.put(URL, {'phone': '+996700999000'}, format='json').status_code, 200)
        response = self.client.put(URL, {'phone': '+996700555666'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '+996700555666')


class DoctorSeesNoPlaceholderEmailTests(APITestCase):
    """N22: в карточке записи врач не видит технический адрес пациента."""

    def test_patient_placeholder_email_hidden_in_appointments(self):
        import datetime

        doctor_user = User.objects.create_user(
            email='doc-ph@example.com', password='password123',
            first_name='Doc', last_name='D', role=User.Role.DOCTOR,
        )
        doctor = DoctorProfile.objects.create(user=doctor_user)
        patient = User.objects.create_user(
            email='996555111222@phone.imbir.kg', password='password123',
            first_name='P', last_name='P', phone='+996555111222',
        )
        Appointment.objects.create(
            patient=patient, doctor=doctor,
            date=datetime.date(2030, 1, 10), time=datetime.time(10, 0),
        )
        self.client.force_authenticate(doctor_user)
        response = self.client.get('/api/doctor/appointments/')
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data['data'] if isinstance(response.data, dict) else response.data
        self.assertEqual(rows[0]['patient']['email'], '')
