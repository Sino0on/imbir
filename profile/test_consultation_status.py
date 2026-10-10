import datetime

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from users.models import DoctorProfile

User = get_user_model()


class PatientAppointmentConsultationStatusTests(APITestCase):
    """K45: в «Истории записей» отдаётся consultation_status — по нему фронт
    прячет «Подключиться» у завершённой видео-консультации."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='cs-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        doctor_user = User.objects.create_user(
            email='cs-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=doctor_user, is_published=True)
        self.client.force_authenticate(self.patient)

    def test_consultation_status_exposed(self):
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=datetime.date(2026, 7, 30), time=datetime.time(10, 0),
            is_online=True, status=Appointment.Status.CONFIRMED,
            consultation_status=Appointment.ConsultationStatus.FINISHED,
        )
        resp = self.client.get('/api/profile/appointments/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        item = next(a for a in resp.data['data'] if a['id'] == appt.id)
        self.assertEqual(item['consultation_status'], 'finished')
