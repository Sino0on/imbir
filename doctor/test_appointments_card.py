import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from users.models import ClinicProfile, DoctorProfile, User


class DoctorAppointmentCardTests(APITestCase):
    """GET /api/doctor/appointments/ отдаёт всё, что нужно врачу в карточке записи:
    комментарий пациента, контакты (в том числе гостя), формат и место приёма."""

    def setUp(self):
        self.doctor_user = User.objects.create_user(
            email='card-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')
        clinic_user = User.objects.create_user(
            email='card-clinic@example.com', password='password123',
            first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=clinic_user, name='Клиника Имбирь', is_published=True)
        self.appt = Appointment.objects.create(
            doctor=self.doctor, clinic=self.clinic,
            date=datetime.date(2030, 1, 10), time=datetime.time(10, 0),
            guest_name='Гость', guest_phone='+996 700 111 222', guest_email='guest@example.com',
            notes='Болит горло', is_online=False,
        )

    def test_card_fields(self):
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.get('/api/doctor/appointments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(a for a in response.data['data'] if a['id'] == self.appt.id)

        self.assertEqual(item['clinic'], {'id': self.clinic.user_id, 'name': 'Клиника Имбирь'})
        self.assertEqual(item['notes'], 'Болит горло')
        self.assertIs(item['is_online'], False)
        self.assertEqual(item['patient']['phone'], '+996 700 111 222')
        self.assertEqual(item['patient']['email'], 'guest@example.com')

    def test_clinic_is_null_without_clinic(self):
        self.appt.clinic = None
        self.appt.save(update_fields=['clinic'])
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.get('/api/doctor/appointments/')
        item = next(a for a in response.data['data'] if a['id'] == self.appt.id)
        self.assertIsNone(item['clinic'])
