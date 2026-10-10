import datetime
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from appointments.models import Appointment
from livekit_integration import services as lk_services
from livekit_integration.permissions import ensure_can_join
from livekit_integration.services import fetch_recording_bytes
from services.models import Service
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


def _event(room_name, identity=''):
    return SimpleNamespace(
        room=SimpleNamespace(name=room_name, sid='RM_test'),
        participant=SimpleNamespace(identity=identity),
    )


@patch('livekit_integration.services.dispatch_summary_task')
class ConsultationLifecycleTests(TestCase):
    """K43/K45: уход единственного участника не завершает консультацию;
    состоявшаяся консультация переводит запись в COMPLETED."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='lc-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='lc-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')
        self.appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=datetime.date(2026, 7, 30), time=datetime.time(10, 0),
            is_online=True, status=Appointment.Status.CONFIRMED,
            room_name='consultation-lc',
        )
        self.room = self.appointment.room_name
        self.patient_identity = f'patient-{self.patient.id}'
        self.doctor_identity = f'doctor-{self.doctor_user.id}'

    def _reload(self):
        self.appointment.refresh_from_db()
        return self.appointment

    def test_only_participant_leaving_does_not_finish(self, dispatch_mock):
        lk_services.handle_participant_joined(_event(self.room, self.patient_identity))
        self.assertEqual(self._reload().consultation_status, Appointment.ConsultationStatus.WAITING)

        lk_services.handle_participant_left(_event(self.room, self.patient_identity))
        appt = self._reload()
        self.assertEqual(appt.consultation_status, Appointment.ConsultationStatus.CREATED)
        self.assertIsNone(appt.ended_at)
        self.assertEqual(appt.status, Appointment.Status.CONFIRMED)
        dispatch_mock.assert_not_called()

    def test_room_finished_before_both_joined_resets_state(self, dispatch_mock):
        lk_services.handle_participant_joined(_event(self.room, self.doctor_identity))
        lk_services.handle_room_finished(_event(self.room))
        appt = self._reload()
        self.assertEqual(appt.consultation_status, Appointment.ConsultationStatus.CREATED)
        self.assertFalse(appt.doctor_joined)
        self.assertEqual(appt.status, Appointment.Status.CONFIRMED)
        dispatch_mock.assert_not_called()

    @override_settings(LIVEKIT_RECORDING_ENABLED=True)
    def test_rejoin_after_solo_wait_starts_new_recording(self, dispatch_mock):
        from livekit import api

        lk_services.handle_participant_joined(_event(self.room, self.doctor_identity))
        Appointment.objects.filter(pk=self.appointment.pk).update(
            doctor_egress_id='EG_wait', doctor_egress_status='EGRESS_COMPLETE',
            doctor_recording_url='/out/wait.ogg',
        )
        self._reload()
        lk_services.handle_participant_left(_event(self.room, self.doctor_identity))
        appt = self._reload()
        self.assertEqual(appt.doctor_egress_id, '')
        self.assertEqual(appt.doctor_recording_url, '')

        lk_services.handle_participant_joined(_event(self.room, self.doctor_identity))
        event = _event(self.room, self.doctor_identity)
        event.track = SimpleNamespace(source=api.TrackSource.MICROPHONE, sid='TR_new')
        info = SimpleNamespace(egress_id='EG_new', status=api.EgressStatus.EGRESS_STARTING)
        with patch('livekit_integration.services.client.run_sync', return_value=info):
            lk_services.handle_track_published(event)
        self.assertEqual(self._reload().doctor_egress_id, 'EG_new')

    def test_room_finished_before_start_clears_wait_recording(self, dispatch_mock):
        lk_services.handle_participant_joined(_event(self.room, self.patient_identity))
        Appointment.objects.filter(pk=self.appointment.pk).update(
            patient_egress_id='EG_wait', patient_egress_status='EGRESS_ACTIVE',
        )
        lk_services.handle_room_finished(_event(self.room))
        appt = self._reload()
        self.assertEqual(appt.patient_egress_id, '')
        self.assertEqual(appt.patient_egress_status, '')

    def test_one_leaves_after_start_keeps_waiting(self, dispatch_mock):
        lk_services.handle_participant_joined(_event(self.room, self.doctor_identity))
        lk_services.handle_participant_joined(_event(self.room, self.patient_identity))
        self.assertEqual(self._reload().consultation_status, Appointment.ConsultationStatus.ACTIVE)

        lk_services.handle_participant_left(_event(self.room, self.patient_identity))
        appt = self._reload()
        self.assertEqual(appt.consultation_status, Appointment.ConsultationStatus.WAITING)
        self.assertEqual(appt.status, Appointment.Status.CONFIRMED)
        dispatch_mock.assert_not_called()

    def test_both_leave_after_start_finishes_and_completes(self, dispatch_mock):
        from notifications.models import Notification

        lk_services.handle_participant_joined(_event(self.room, self.doctor_identity))
        lk_services.handle_participant_joined(_event(self.room, self.patient_identity))
        lk_services.handle_participant_left(_event(self.room, self.patient_identity))
        lk_services.handle_participant_left(_event(self.room, self.doctor_identity))

        appt = self._reload()
        self.assertEqual(appt.consultation_status, Appointment.ConsultationStatus.FINISHED)
        self.assertIsNotNone(appt.ended_at)
        self.assertEqual(appt.status, Appointment.Status.COMPLETED)
        dispatch_mock.assert_called_once()
        self.assertTrue(Notification.objects.filter(
            user=self.patient, type=Notification.Type.APPOINTMENT_COMPLETED,
        ).exists())

    def test_room_finished_after_start_completes(self, dispatch_mock):
        lk_services.handle_participant_joined(_event(self.room, self.doctor_identity))
        lk_services.handle_participant_joined(_event(self.room, self.patient_identity))
        lk_services.handle_room_finished(_event(self.room))
        appt = self._reload()
        self.assertEqual(appt.consultation_status, Appointment.ConsultationStatus.FINISHED)
        self.assertEqual(appt.status, Appointment.Status.COMPLETED)

    def test_finish_does_not_override_cancelled_appointment(self, dispatch_mock):
        lk_services.handle_participant_joined(_event(self.room, self.doctor_identity))
        lk_services.handle_participant_joined(_event(self.room, self.patient_identity))
        Appointment.objects.filter(pk=self.appointment.pk).update(status=Appointment.Status.CANCELLED)
        lk_services.handle_room_finished(_event(self.room))
        self.assertEqual(self._reload().status, Appointment.Status.CANCELLED)


@override_settings(LIVEKIT_JOIN_WINDOW_MINUTES=15)
class LateJoinTests(TestCase):
    """K44: опоздавший (>15 мин) может войти, пока его ждут, или до конца приёма."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='late-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='late-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')

    def _appointment(self, minutes_ago, **kwargs):
        start = timezone.localtime() - datetime.timedelta(minutes=minutes_ago)
        return Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=start.date(), time=start.time().replace(microsecond=0),
            is_online=True, status=Appointment.Status.CONFIRMED, **kwargs,
        )

    def test_late_rejected_when_nobody_waits(self):
        appt = self._appointment(20)
        with self.assertRaises(ValidationError):
            ensure_can_join(appt, self.patient)

    def test_late_allowed_while_other_waits(self):
        appt = self._appointment(
            20, consultation_status=Appointment.ConsultationStatus.WAITING, doctor_joined=True,
        )
        self.assertEqual(ensure_can_join(appt, self.patient), 'patient')

    def test_late_allowed_within_service_duration(self):
        service = Service.objects.create(name='Онлайн-приём', category='Онлайн', price=1000, duration=60)
        appt = self._appointment(40, service=service)
        self.assertEqual(ensure_can_join(appt, self.patient), 'patient')

    def test_rejected_after_service_duration(self):
        service = Service.objects.create(name='Онлайн-приём', category='Онлайн', price=1000, duration=30)
        appt = self._appointment(40, service=service)
        with self.assertRaises(ValidationError):
            ensure_can_join(appt, self.patient)
