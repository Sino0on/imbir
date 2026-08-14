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


class ConsultationSummaryTaskTests(APITestCase):
    """generate_consultation_summary: должен ждать готовности записи и не падать без неё."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='summary-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='summary-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')
        self.appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=datetime.date(2026, 7, 30), time=datetime.time(10, 0),
            is_online=True,
        )

    def test_no_recording_skips_summary(self):
        from appointments.tasks import generate_consultation_summary

        with patch('appointments.ai_summary.generate_and_deliver_summary') as mock_gen:
            generate_consultation_summary.run(self.appointment.id)
        mock_gen.assert_not_called()

    def test_both_roles_failed_skips_summary(self):
        from appointments.tasks import generate_consultation_summary

        self.appointment.doctor_egress_id = 'EG_doc'
        self.appointment.doctor_egress_status = 'EGRESS_FAILED'
        self.appointment.patient_egress_id = 'EG_pat'
        self.appointment.patient_egress_status = 'EGRESS_FAILED'
        self.appointment.save(update_fields=[
            'doctor_egress_id', 'doctor_egress_status', 'patient_egress_id', 'patient_egress_status',
        ])

        with patch('appointments.ai_summary.generate_and_deliver_summary') as mock_gen:
            generate_consultation_summary.run(self.appointment.id)
        mock_gen.assert_not_called()

    def test_one_role_not_ready_retries(self):
        """Врач уже готов, пациент ещё пишется — задача должна ждать обе стороны."""
        from appointments.tasks import generate_consultation_summary

        self.appointment.doctor_egress_id = 'EG_doc'
        self.appointment.doctor_egress_status = 'EGRESS_COMPLETE'
        self.appointment.doctor_recording_url = 'https://example.com/doctor.ogg'
        self.appointment.patient_egress_id = 'EG_pat'
        self.appointment.patient_egress_status = 'EGRESS_ACTIVE'
        self.appointment.save(update_fields=[
            'doctor_egress_id', 'doctor_egress_status', 'doctor_recording_url',
            'patient_egress_id', 'patient_egress_status',
        ])

        with patch.object(generate_consultation_summary, 'retry', side_effect=Exception('retried')) as mock_retry:
            with self.assertRaises(Exception):
                generate_consultation_summary.run(self.appointment.id)
        mock_retry.assert_called_once()

    def test_recording_ready_generates_summary(self):
        from appointments.tasks import generate_consultation_summary

        self.appointment.doctor_egress_id = 'EG_doc'
        self.appointment.doctor_egress_status = 'EGRESS_COMPLETE'
        self.appointment.doctor_recording_url = 'https://example.com/doctor.ogg'
        self.appointment.patient_egress_id = 'EG_pat'
        self.appointment.patient_egress_status = 'EGRESS_COMPLETE'
        self.appointment.patient_recording_url = 'https://example.com/patient.ogg'
        self.appointment.save(update_fields=[
            'doctor_egress_id', 'doctor_egress_status', 'doctor_recording_url',
            'patient_egress_id', 'patient_egress_status', 'patient_recording_url',
        ])

        with patch('appointments.ai_summary.generate_and_deliver_summary') as mock_gen:
            generate_consultation_summary.run(self.appointment.id)
        mock_gen.assert_called_once()

    def test_patient_never_spoke_still_generates_summary(self):
        """Пациент не публиковал микрофон (egress не запускался) — не ждём его вечно,
        строим резюме по тому, что есть у врача."""
        from appointments.tasks import generate_consultation_summary

        self.appointment.doctor_egress_id = 'EG_doc'
        self.appointment.doctor_egress_status = 'EGRESS_COMPLETE'
        self.appointment.doctor_recording_url = 'https://example.com/doctor.ogg'
        self.appointment.save(update_fields=[
            'doctor_egress_id', 'doctor_egress_status', 'doctor_recording_url',
        ])

        with patch('appointments.ai_summary.generate_and_deliver_summary') as mock_gen:
            generate_consultation_summary.run(self.appointment.id)
        mock_gen.assert_called_once()


class ConsultationSummaryDeliveryTests(APITestCase):
    """send_summary_to_chat: резюме должно попадать в комнату врач-пациент как системное сообщение."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='delivery-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='delivery-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')
        self.appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=datetime.date(2026, 7, 30), time=datetime.time(10, 0),
            is_online=True,
        )

    def test_send_summary_creates_system_message_in_shared_room(self):
        from appointments.ai_summary import send_summary_to_chat
        from chat.models import ChatRoom

        send_summary_to_chat(self.appointment, 'Тестовое резюме консультации.')

        room = ChatRoom.objects.get(participants=self.patient)
        self.assertTrue(room.participants.filter(id=self.doctor_user.id).exists())
        msg = room.messages.last()
        self.assertIsNone(msg.sender)
        self.assertIn('Тестовое резюме консультации.', msg.content)

    def test_send_summary_without_patient_is_noop(self):
        from appointments.ai_summary import send_summary_to_chat
        from chat.models import ChatRoom

        self.appointment.patient = None
        self.appointment.save(update_fields=['patient'])

        send_summary_to_chat(self.appointment, 'резюме')
        self.assertEqual(ChatRoom.objects.count(), 0)


class AppointmentStatusUpdateTests(APITestCase):
    """PATCH /api/appointments/{id}/ — переходы статуса, не только отмена."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='status-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='status-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')
        self.appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=datetime.date(2026, 8, 20), time=datetime.time(10, 0),
            status=Appointment.Status.PENDING,
        )
        self.url = f'/api/appointments/{self.appointment.pk}/'

    def test_doctor_confirms_pending_appointment(self):
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'confirmed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'confirmed')

    def test_doctor_completes_confirmed_appointment(self):
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.save(update_fields=['status'])

        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'completed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'completed')

    def test_doctor_completes_pending_appointment_directly(self):
        # Разрешено пропустить "confirmed" и сразу завершить — не все записи
        # проходят через явное подтверждение.
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'completed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'completed')

    def test_cannot_change_status_of_completed_appointment(self):
        self.appointment.status = Appointment.Status.COMPLETED
        self.appointment.save(update_fields=['status'])

        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'cancelled'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_change_status_of_cancelled_appointment(self):
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.save(update_fields=['status'])

        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'confirmed'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_can_cancel(self):
        self.client.force_authenticate(user=self.patient)
        response = self.client.patch(self.url, {'status': 'cancelled'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'cancelled')

    def test_patient_cannot_confirm(self):
        self.client.force_authenticate(user=self.patient)
        response = self.client.patch(self.url, {'status': 'confirmed'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.PENDING)

    def test_patient_cannot_complete(self):
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.save(update_fields=['status'])

        self.client.force_authenticate(user=self.patient)
        response = self.client.patch(self.url, {'status': 'completed'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_status_rejected(self):
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'pending'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AppointmentOverlapTests(APITestCase):
    """Запись к врачу учитывает длительность услуги — второй пациент не может
    занять время, которое уже перекрывается существующей записью."""

    def setUp(self):
        from services.models import Service

        self.doctor_user = User.objects.create_user(
            email='overlap-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек',
            # 2026-09-01 — вторник; окно шире того, что используют тесты ниже.
            schedule={'tuesday': {'from': '09:00', 'to': '18:00', 'enabled': True}},
        )
        self.patient1 = User.objects.create_user(
            email='overlap-patient1@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.patient2 = User.objects.create_user(
            email='overlap-patient2@example.com', password='password123',
            first_name='Petr', role=User.Role.PATIENT,
        )
        self.service_60min = Service.objects.create(
            name='Приём (час)', category='general', duration=60, is_active=True,
        )
        self.create_url = '/api/appointments/'

    def test_second_patient_cannot_book_overlapping_slot(self):
        self.client.force_authenticate(user=self.patient1)
        r1 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': '2026-09-01', 'time': '10:00',
        })
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.patient2)
        r2 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'date': '2026-09-01', 'time': '10:30',  # внутри 10:00-11:00 первой записи
        })
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_second_patient_can_book_after_service_ends(self):
        self.client.force_authenticate(user=self.patient1)
        r1 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': '2026-09-01', 'time': '10:00',
        })
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.patient2)
        r2 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'date': '2026-09-01', 'time': '11:00',  # ровно после окончания часовой записи
        })
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)

    def test_reschedule_into_occupied_slot_rejected(self):
        self.client.force_authenticate(user=self.patient1)
        self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': '2026-09-01', 'time': '10:00',
        })

        self.client.force_authenticate(user=self.patient2)
        other = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'date': '2026-09-01', 'time': '12:00',
        }).data

        response = self.client.post(f"/api/appointments/{other['id']}/reschedule/", {
            'date': '2026-09-01', 'time': '10:15',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_available_slots_blocked_for_full_service_duration(self):
        self.client.force_authenticate(user=self.patient1)
        self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': '2026-09-01', 'time': '10:00',
        })

        response = self.client.get(
            f'/api/doctors/{self.doctor_user.id}/available-slots/', {'date': '2026-09-01'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slots_by_time = {s['time']: s['available'] for s in response.data['slots']}

        self.assertFalse(slots_by_time.get('10:00'))
        self.assertFalse(slots_by_time.get('10:30'))
        self.assertTrue(slots_by_time.get('11:00'))

    def test_available_slots_respects_requested_service_duration(self):
        self.client.force_authenticate(user=self.patient1)
        self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'date': '2026-09-01', 'time': '11:30',  # 30-минутная запись по умолчанию
        })

        # Спрашиваем часовую услугу в 11:00 — она бы заняла и 11:30, где уже занято.
        response = self.client.get(
            f'/api/doctors/{self.doctor_user.id}/available-slots/',
            {'date': '2026-09-01', 'service_id': self.service_60min.id},
        )
        slots_by_time = {s['time']: s['available'] for s in response.data['slots']}
        self.assertFalse(slots_by_time.get('11:00'))
