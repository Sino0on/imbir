from rest_framework.test import APITestCase
from rest_framework import status
from users.models import User, DoctorProfile
from appointments.models import Appointment
import datetime


from unittest.mock import patch

class AppointmentRescheduleTests(APITestCase):
    def setUp(self):
        # Create users
        self.patient = User.objects.create_user(
            email='patient@example.com', password='password123', first_name='Ivan', role=User.Role.PATIENT
        )
        self.doctor_user = User.objects.create_user(
            email='doctor@example.com', password='password123', first_name='Doc', role=User.Role.DOCTOR
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек'
        )

        self.other_user = User.objects.create_user(
            email='other@example.com', password='password123', first_name='Other', role=User.Role.PATIENT
        )

        # Create appointment
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            date=datetime.date(2026, 8, 1),
            time=datetime.time(10, 0),
            is_online=True,
            google_meet_link='https://meet.google.com/old-link',
            status=Appointment.Status.PENDING
        )

        self.reschedule_url = f'/api/appointments/{self.appointment.pk}/reschedule/'

    def test_reschedule_unauthorized(self):
        response = self.client.post(self.reschedule_url, {'date': '2026-08-02', 'time': '11:00'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reschedule_unauthorized_user(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.reschedule_url, {'date': '2026-08-02', 'time': '11:00'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('appointments.views.generate_meet_link')
    def test_reschedule_success(self, mock_generate_meet):
        mock_generate_meet.return_value = 'https://meet.google.com/new-link'
        self.client.force_authenticate(user=self.patient)

        # Before reschedule
        old_meet_link = self.appointment.google_meet_link

        response = self.client.post(self.reschedule_url, {
            'date': '2026-08-05',
            'time': '14:30'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify response and database update
        self.assertEqual(response.data['date'], '2026-08-05')
        self.assertEqual(response.data['time'], '14:30:00')

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.date, datetime.date(2026, 8, 5))
        self.assertEqual(self.appointment.time, datetime.time(14, 30))
        
        # Google Meet link should be updated/regenerated
        self.assertEqual(self.appointment.google_meet_link, 'https://meet.google.com/new-link')
        self.assertNotEqual(self.appointment.google_meet_link, old_meet_link)

    def test_reschedule_cancelled_appointment(self):
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.save()

        self.client.force_authenticate(user=self.patient)
        response = self.client.post(self.reschedule_url, {
            'date': '2026-08-05',
            'time': '14:30'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Нельзя перенести отменённую запись.', str(response.data))

    def test_reschedule_completed_appointment(self):
        self.appointment.status = Appointment.Status.COMPLETED
        self.appointment.save()

        self.client.force_authenticate(user=self.patient)
        response = self.client.post(self.reschedule_url, {
            'date': '2026-08-05',
            'time': '14:30'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Нельзя перенести завершённую запись.', str(response.data))
