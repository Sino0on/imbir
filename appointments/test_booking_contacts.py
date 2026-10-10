import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from users.models import ClinicProfile, DoctorClinicLink, DoctorProfile, User


def _next_weekday(weekday):
    from django.utils import timezone

    today = timezone.localdate()
    return today + datetime.timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


def _items(response):
    data = response.data
    if isinstance(data, dict):
        data = data.get('data', data.get('results', data))
    return data


class AuthenticatedBookingContactTests(APITestCase):
    """N64: контакт на визит, который вошедший пациент указал в форме записи
    (другое имя, телефон, которого нет в аккаунте), не теряется — он хранится
    в guest_* и показывается врачу и клинике впереди данных аккаунта."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='mother@example.com', password='password123',
            first_name='Айгуль', last_name='Иванова', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='contact-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек',
            schedule={'wednesday': {'from': '09:00', 'to': '18:00', 'enabled': True}},
        )
        self.clinic_user = User.objects.create_user(
            email='contact-clinic@example.com', password='password123',
            first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Клиника', is_published=True,
        )
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic, is_active=True)
        self.day = _next_weekday(2).isoformat()

    def book(self, **contact):
        self.client.force_authenticate(user=self.patient)
        response = self.client.post('/api/appointments/', {
            'doctor_id': self.doctor_user.id, 'clinic_id': self.clinic_user.id,
            'date': self.day, 'time': '10:00', **contact,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Appointment.objects.latest('id')

    def test_contact_that_differs_from_account_is_stored(self):
        appt = self.book(
            guest_name='Тимур Иванов', guest_phone='+77011234567', guest_email='kid@example.com',
        )
        self.assertEqual(appt.patient, self.patient)
        self.assertEqual(appt.guest_name, 'Тимур Иванов')
        self.assertEqual(appt.guest_phone, '+77011234567')
        self.assertEqual(appt.guest_email, 'kid@example.com')

    def test_contact_equal_to_account_is_not_duplicated(self):
        self.patient.phone = '+996700123456'
        self.patient.save(update_fields=['phone'])
        appt = self.book(
            guest_name=' айгуль  Иванова ', guest_phone='+996 700 123 456',
            guest_email='Mother@Example.com',
        )
        self.assertEqual((appt.guest_name, appt.guest_phone, appt.guest_email), ('', '', ''))

    def test_booking_without_contact_still_works(self):
        appt = self.book()
        self.assertEqual(appt.patient, self.patient)
        self.assertEqual(appt.guest_phone, '')

    def test_doctor_sees_visit_contact_before_account_data(self):
        appt = self.book(guest_name='Тимур Иванов', guest_phone='+996555000111')
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.get('/api/doctor/appointments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(a for a in _items(response) if a['id'] == appt.id)
        self.assertEqual(item['patient']['id'], self.patient.id)
        self.assertEqual(item['patient']['full_name'], 'Тимур Иванов')
        self.assertEqual(item['patient']['phone'], '+996555000111')
        # Почту не меняли — берётся из аккаунта.
        self.assertEqual(item['patient']['email'], 'mother@example.com')

    def test_clinic_sees_visit_contact_before_account_data(self):
        appt = self.book(guest_phone='+996555000111')
        self.client.force_authenticate(user=self.clinic_user)
        response = self.client.get('/api/clinic/appointments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(a for a in _items(response) if a['id'] == appt.id)
        self.assertEqual(item['patient']['id'], self.patient.id)
        self.assertEqual(item['patient']['full_name'], self.patient.full_name)
        self.assertEqual(item['patient']['phone'], '+996555000111')

    def test_appointment_detail_shows_visit_contact(self):
        appt = self.book(guest_phone='+996555000111')
        self.client.force_authenticate(user=self.patient)
        response = self.client.get(f'/api/appointments/{appt.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['patient']['phone'], '+996555000111')
        self.assertEqual(response.data['patient']['full_name'], self.patient.full_name)

    def test_guest_booking_is_unchanged(self):
        response = self.client.post('/api/appointments/', {
            'doctor_id': self.doctor_user.id, 'date': self.day, 'time': '11:00',
            'guest_name': 'Гость', 'guest_phone': '+77011234567',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        appt = Appointment.objects.latest('id')
        self.assertIsNone(appt.patient)
        self.assertEqual(appt.guest_phone, '+77011234567')
