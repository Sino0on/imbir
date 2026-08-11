import datetime
import os
import tempfile

from django.test import TestCase, override_settings

from appointments.models import Appointment
from livekit_integration.services import fetch_recording_bytes
from users.models import DoctorProfile, User


class FetchRecordingBytesTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            email='rec-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='rec-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')
        self.appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=datetime.date(2026, 7, 30), time=datetime.time(10, 0),
            is_online=True,
        )

    def test_empty_recording_url_raises(self):
        with self.assertRaises(ValueError):
            fetch_recording_bytes(self.appointment, 'doctor')

    @override_settings(LIVEKIT_S3_BUCKET='')
    def test_local_path_reads_file(self):
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
            f.write(b'fake-audio-bytes')
            path = f.name
        try:
            self.appointment.doctor_recording_url = path
            content, filename = fetch_recording_bytes(self.appointment, 'doctor')
            self.assertEqual(content, b'fake-audio-bytes')
            self.assertEqual(filename, os.path.basename(path))
        finally:
            os.remove(path)
