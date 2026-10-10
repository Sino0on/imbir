from rest_framework.test import APITestCase
from rest_framework import status
from users.models import User, DoctorProfile
from appointments.models import Appointment
import datetime


from unittest.mock import patch

from django.utils import timezone


def _next_weekday(weekday):
    """Ближайшая будущая дата с этим днём недели (0 — понедельник). Слоты на
    прошедшие дни всегда заняты, поэтому жёстко прописанная дата ломала тесты,
    как только наступала."""
    today = timezone.localdate()
    return today + datetime.timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


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
            user=self.doctor_user, is_published=True, city='Бишкек',
            # self.new_day, куда переносят запись ниже, — среда.
            schedule={'wednesday': {'from': '09:00', 'to': '18:00', 'enabled': True}},
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
        # Перенос в прошлое запрещён, поэтому дата — ближайшая будущая среда,
        # а не жёстко прописанная (2026-08-05 уже прошла).
        self.new_day = _next_weekday(2).isoformat()

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
            'date': self.new_day,
            'time': '14:30'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify response and database update
        self.assertEqual(response.data['date'], self.new_day)
        self.assertEqual(response.data['time'], '14:30:00')

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.date, datetime.date.fromisoformat(self.new_day))
        self.assertEqual(self.appointment.time, datetime.time(14, 30))
        
        # Google Meet link should be updated/regenerated
        self.assertEqual(self.appointment.google_meet_link, 'https://meet.google.com/new-link')
        self.assertNotEqual(self.appointment.google_meet_link, old_meet_link)

    def test_reschedule_cancelled_appointment(self):
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.save()

        self.client.force_authenticate(user=self.patient)
        response = self.client.post(self.reschedule_url, {
            'date': self.new_day,
            'time': '14:30'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Нельзя перенести отменённую запись.', str(response.data))

    def test_reschedule_completed_appointment(self):
        self.appointment.status = Appointment.Status.COMPLETED
        self.appointment.save()

        self.client.force_authenticate(user=self.patient)
        response = self.client.post(self.reschedule_url, {
            'date': self.new_day,
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
            # self.day — вторник; окно шире того, что используют тесты ниже.
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
        # Записаться можно только на услугу самого врача.
        self.doctor.services.add(self.service_60min)
        self.create_url = '/api/appointments/'
        self.day = _next_weekday(1).isoformat()

    def test_second_patient_cannot_book_overlapping_slot(self):
        self.client.force_authenticate(user=self.patient1)
        r1 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': self.day, 'time': '10:00',
        })
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.patient2)
        r2 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'date': self.day, 'time': '10:30',  # внутри 10:00-11:00 первой записи
        })
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_second_patient_can_book_after_service_ends(self):
        self.client.force_authenticate(user=self.patient1)
        r1 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': self.day, 'time': '10:00',
        })
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.patient2)
        r2 = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'date': self.day, 'time': '11:00',  # ровно после окончания часовой записи
        })
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)

    def test_reschedule_into_occupied_slot_rejected(self):
        self.client.force_authenticate(user=self.patient1)
        self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': self.day, 'time': '10:00',
        })

        self.client.force_authenticate(user=self.patient2)
        other = self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'date': self.day, 'time': '12:00',
        }).data

        response = self.client.post(f"/api/appointments/{other['id']}/reschedule/", {
            'date': self.day, 'time': '10:15',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_available_slots_blocked_for_full_service_duration(self):
        self.client.force_authenticate(user=self.patient1)
        self.client.post(self.create_url, {
            'doctor_id': self.doctor_user.id,
            'service_id': self.service_60min.id,
            'date': self.day, 'time': '10:00',
        })

        response = self.client.get(
            f'/api/doctors/{self.doctor_user.id}/available-slots/', {'date': self.day},
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
            'date': self.day, 'time': '11:30',  # 30-минутная запись по умолчанию
        })

        # Спрашиваем часовую услугу в 11:00 — она бы заняла и 11:30, где уже занято.
        response = self.client.get(
            f'/api/doctors/{self.doctor_user.id}/available-slots/',
            {'date': self.day, 'service_id': self.service_60min.id},
        )
        slots_by_time = {s['time']: s['available'] for s in response.data['slots']}
        self.assertFalse(slots_by_time.get('11:00'))


class ServiceDurationScheduleTests(APITestCase):
    """Длительность услуги должна целиком помещаться в рабочий день врача и не
    задевать его перерыв — и в слотах, и при создании/переносе записи."""

    def setUp(self):
        from services.models import Service

        self.day = _next_weekday(2).isoformat()  # среда
        self.sunday = _next_weekday(6).isoformat()
        self.doctor_user = User.objects.create_user(
            email='duration-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек',
            schedule={
                'wednesday': {'from': '09:00', 'to': '18:00', 'enabled': True},
                'sunday': {'from': '09:00', 'to': '18:00', 'enabled': False},
            },
            lunch_break={'from': '13:00', 'to': '14:00'},
        )
        self.patient = User.objects.create_user(
            email='duration-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.other_patient = User.objects.create_user(
            email='duration-other@example.com', password='password123',
            first_name='Petr', role=User.Role.PATIENT,
        )
        self.massage = Service.objects.create(
            name='Массаж', category='general', duration=60, is_active=True,
        )
        self.doctor.services.add(self.massage)

    def book(self, time, service=None, date=None):
        data = {
            'doctor_id': self.doctor_user.id, 'date': date or self.day, 'time': time,
            'guest_name': 'Тест', 'guest_phone': '+996 700 000 000',
        }
        if service:
            data['service_id'] = service.id
        return self.client.post('/api/appointments/', data)

    def slots(self, service=None, **extra):
        params = {'date': self.day, **extra}
        if service:
            params['service_id'] = service.id
        response = self.client.get(f'/api/doctors/{self.doctor_user.id}/available-slots/', params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {s['time']: s['available'] for s in response.data['slots']}

    def test_slots_hide_times_where_the_service_does_not_fit(self):
        default, massage = self.slots(), self.slots(self.massage)
        self.assertTrue(default['12:30'] and default['17:30'])
        # Часовая сетка: 12:30 и 17:30 в ней нет, перерыв 13:00–14:00 занят,
        # последний приём 17:00–18:00 укладывается в день.
        self.assertNotIn('12:30', massage)
        self.assertNotIn('17:30', massage)
        self.assertFalse(massage['13:00'])
        self.assertTrue(massage['12:00'] and massage['14:00'] and massage['17:00'])

    def test_slot_grid_follows_service_duration(self):
        from services.models import Service

        consult = Service.objects.create(
            name='Консультация', category='general', duration=45, is_active=True,
        )
        slots = self.slots(consult)
        # Шаг 45 мин. 12:45 и 13:30 задевают перерыв 13:00–14:00, после него
        # сетка продолжается ровно с 14:00; 17:45–18:30 в день уже не влезает.
        self.assertEqual(
            list(slots),
            ['09:00', '09:45', '10:30', '11:15', '12:00', '12:45',
             '13:30', '14:00', '14:45', '15:30', '16:15', '17:00'],
        )
        self.assertEqual([t for t, ok in slots.items() if not ok], ['12:45', '13:30'])

    def test_slot_grid_continues_right_after_a_booking(self):
        from services.models import Service

        consult = Service.objects.create(
            name='Консультация', category='general', duration=45, is_active=True,
        )
        self.doctor.services.add(consult)
        self.assertEqual(self.book('10:00').status_code, status.HTTP_201_CREATED)  # 10:00–10:30
        slots = self.slots(consult)
        # 09:45–10:30 задевает запись; следующий слот — сразу в 10:30, а не в 11:15.
        self.assertTrue(slots['09:00'])
        self.assertFalse(slots['09:45'])
        self.assertTrue(slots['10:30'])
        self.assertEqual(self.book('10:30', consult).status_code, status.HTTP_201_CREATED)

    def test_create_rejects_service_running_past_working_hours(self):
        response = self.book('17:30', self.massage)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('рабочее время', str(response.data['time']))

    def test_create_rejects_service_overlapping_lunch(self):
        response = self.book('12:30', self.massage)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('перерыв', str(response.data['time']))

    def test_create_rejects_day_off(self):
        response = self.book('10:00', date=self.sunday)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_accepts_times_that_fit(self):
        self.assertEqual(self.book('17:00', self.massage).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.book('12:30').status_code, status.HTTP_201_CREATED)  # 30 мин по умолчанию

    def test_reschedule_checks_the_service_duration(self):
        self.client.force_authenticate(user=self.patient)
        created = self.book('10:00', self.massage)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        url = f"/api/appointments/{created.data['id']}/reschedule/"

        self.assertEqual(
            self.client.post(url, {'date': self.day, 'time': '17:30'}).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(url, {'date': self.day, 'time': '15:00'}).status_code,
            status.HTTP_200_OK,
        )

    def test_reschedule_slots_ignore_own_appointment_only_for_its_owner(self):
        self.client.force_authenticate(user=self.patient)
        created = self.book('10:00', self.massage)
        own_id = created.data['id']

        self.assertTrue(self.slots(self.massage, exclude_appointment_id=own_id)['10:00'])

        self.client.force_authenticate(user=self.other_patient)
        self.assertFalse(self.slots(self.massage, exclude_appointment_id=own_id)['10:00'])

        self.client.force_authenticate(user=None)
        self.assertFalse(self.slots(self.massage, exclude_appointment_id=own_id)['10:00'])


def _future_day(days=7):
    return timezone.localdate() + datetime.timedelta(days=days)


def _all_week(frm='09:00', to='18:00'):
    return {
        day: {'from': frm, 'to': to, 'enabled': True}
        for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
    }


class BookingServiceAndClinicValidationTests(APITestCase):
    """K8: услуга и клиника в записи проверяются, а не молча отбрасываются;
    запись в прошлое запрещена — в том числе запись только в клинику."""

    def setUp(self):
        from services.models import Service
        from users.models import ClinicProfile, DoctorClinicLink

        self.doctor_user = User.objects.create_user(
            email='k8-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек', schedule=_all_week(),
        )
        self.other_doctor_user = User.objects.create_user(
            email='k8-other-doctor@example.com', password='password123',
            first_name='Other', role=User.Role.DOCTOR,
        )
        self.other_doctor = DoctorProfile.objects.create(
            user=self.other_doctor_user, is_published=True, city='Бишкек', schedule=_all_week(),
        )
        self.clinic_user = User.objects.create_user(
            email='k8-clinic@example.com', password='password123',
            first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=self.clinic_user, name='Клиника', is_published=True)
        self.other_clinic_user = User.objects.create_user(
            email='k8-clinic2@example.com', password='password123',
            first_name='Clinic2', role=User.Role.CLINIC,
        )
        self.other_clinic = ClinicProfile.objects.create(
            user=self.other_clinic_user, name='Другая клиника', is_published=True,
        )
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic, is_active=True)

        self.own_service = Service.objects.create(name='Своя', category='general', duration=30, clinic=self.clinic)
        self.doctor.services.add(self.own_service)
        self.foreign_service = Service.objects.create(name='Чужая', category='general', duration=30)
        self.other_doctor.services.add(self.foreign_service)
        self.inactive_service = Service.objects.create(
            name='Выключена', category='general', duration=30, is_active=False,
        )
        self.doctor.services.add(self.inactive_service)
        # Услуга клиники без закреплённых врачей — её может оказать любой врач клиники.
        self.clinic_wide_service = Service.objects.create(
            name='Общая', category='general', duration=30, clinic=self.clinic,
        )
        self.other_clinic_service = Service.objects.create(
            name='В другой клинике', category='general', duration=30, clinic=self.other_clinic,
        )

        self.day = _future_day().isoformat()

    def book(self, **extra):
        data = {
            'date': self.day, 'time': '10:00',
            'guest_name': 'Гость', 'guest_phone': '+996 700 000 000',
            **extra,
        }
        return self.client.post('/api/appointments/', data)

    def test_own_service_accepted(self):
        response = self.book(doctor_id=self.doctor_user.id, service_id=self.own_service.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['service']['id'], self.own_service.id)

    def test_nonexistent_service_rejected(self):
        response = self.book(doctor_id=self.doctor_user.id, service_id=999999)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service_id', response.data)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_inactive_service_rejected(self):
        response = self.book(doctor_id=self.doctor_user.id, service_id=self.inactive_service.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service_id', response.data)

    def test_other_doctors_service_rejected(self):
        response = self.book(doctor_id=self.doctor_user.id, service_id=self.foreign_service.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service_id', response.data)

    def test_clinic_wide_service_accepted_for_doctor_of_that_clinic(self):
        response = self.book(
            doctor_id=self.doctor_user.id, clinic_id=self.clinic_user.id,
            service_id=self.clinic_wide_service.id,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_clinic_wide_service_rejected_for_doctor_outside_clinic(self):
        response = self.book(doctor_id=self.other_doctor_user.id, service_id=self.clinic_wide_service.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_clinic_not_linked_to_doctor_rejected(self):
        response = self.book(doctor_id=self.doctor_user.id, clinic_id=self.other_clinic_user.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('clinic_id', response.data)

    def test_inactive_link_rejected(self):
        from users.models import DoctorClinicLink

        DoctorClinicLink.objects.filter(doctor=self.doctor).update(is_active=False)
        response = self.book(doctor_id=self.doctor_user.id, clinic_id=self.clinic_user.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_service_from_another_clinic_rejected(self):
        response = self.book(clinic_id=self.clinic_user.id, service_id=self.other_clinic_service.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service_id', response.data)

    def test_clinic_only_booking_with_own_service_accepted(self):
        response = self.book(clinic_id=self.clinic_user.id, service_id=self.clinic_wide_service.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_past_date_rejected_for_doctor(self):
        yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        response = self.book(doctor_id=self.doctor_user.id, date=yesterday)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('time', response.data)

    def test_past_date_rejected_for_clinic_only_booking(self):
        yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        response = self.book(clinic_id=self.clinic_user.id, date=yesterday)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('time', response.data)


class CompleteFutureAppointmentTests(APITestCase):
    """K12: завершить приём до его начала нельзя."""

    def setUp(self):
        self.patient = User.objects.create_user(
            email='k12-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='k12-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True, city='Бишкек')

    def _appointment(self, date, status_value=Appointment.Status.CONFIRMED):
        return Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            date=date, time=datetime.time(10, 0), status=status_value,
        )

    def test_future_appointment_cannot_be_completed(self):
        from notifications.models import Notification

        self.client.force_authenticate(user=self.doctor_user)
        for status_value in (Appointment.Status.PENDING, Appointment.Status.CONFIRMED):
            appt = self._appointment(_future_day(3), status_value)
            response = self.client.patch(f'/api/appointments/{appt.pk}/', {'status': 'completed'})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            appt.refresh_from_db()
            self.assertEqual(appt.status, status_value)
        self.assertFalse(
            Notification.objects.filter(type=Notification.Type.APPOINTMENT_COMPLETED).exists()
        )

    def test_past_appointment_can_be_completed(self):
        appt = self._appointment(timezone.localdate() - datetime.timedelta(days=1))
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(f'/api/appointments/{appt.pk}/', {'status': 'completed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_future_appointment_can_still_be_confirmed_and_cancelled(self):
        appt = self._appointment(_future_day(3), Appointment.Status.PENDING)
        self.client.force_authenticate(user=self.doctor_user)
        self.assertEqual(
            self.client.patch(f'/api/appointments/{appt.pk}/', {'status': 'confirmed'}).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.patch(f'/api/appointments/{appt.pk}/', {'status': 'cancelled'}).status_code,
            status.HTTP_200_OK,
        )


class GuestAppointmentNotificationTests(APITestCase):
    """K5: гость без аккаунта узнаёт о подтверждении/отмене/переносе по SMS и почте;
    анонимный посетитель гостевой записи не может сам её подтвердить."""

    def setUp(self):
        self.doctor_user = User.objects.create_user(
            email='k5-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек', schedule=_all_week(),
        )
        self.appt = Appointment.objects.create(
            doctor=self.doctor, date=_future_day(3), time=datetime.time(10, 0),
            guest_name='Гость', guest_phone='+996 700 111 222', guest_email='guest@example.com',
        )
        self.url = f'/api/appointments/{self.appt.pk}/'

    @patch('users.utils.send_sms_nikita')
    def test_guest_notified_on_confirm(self, mock_sms):
        from django.core import mail

        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'confirmed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_sms.assert_called_once()
        self.assertEqual(mock_sms.call_args[0][0], '+996 700 111 222')
        self.assertIn('подтверждена', mock_sms.call_args[0][1])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['guest@example.com'])

    @patch('users.utils.send_sms_nikita')
    def test_guest_notified_on_cancel_by_doctor(self, mock_sms):
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.patch(self.url, {'status': 'cancelled'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_sms.assert_called_once()
        self.assertIn('отменена', mock_sms.call_args[0][1])

    @patch('users.utils.send_sms_nikita')
    def test_guest_notified_on_reschedule_by_doctor(self, mock_sms):
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.post(f'{self.url}reschedule/', {
            'date': _future_day(4).isoformat(), 'time': '11:00',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_sms.assert_called_once()
        self.assertIn('перенесена', mock_sms.call_args[0][1])

    @patch('users.utils.send_sms_nikita')
    def test_anonymous_cancel_notifies_doctor_not_guest(self, mock_sms):
        from notifications.models import Notification

        response = self.client.patch(self.url, {'status': 'cancelled'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_sms.assert_not_called()
        self.assertTrue(Notification.objects.filter(
            user=self.doctor_user, type=Notification.Type.APPOINTMENT_CANCELLED,
        ).exists())

    def test_anonymous_cannot_confirm_guest_appointment(self):
        response = self.client.patch(self.url, {'status': 'confirmed'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, Appointment.Status.PENDING)


class RescheduleRulesTests(APITestCase):
    """K10/K46/K15: перенос — не в прошлое, с уведомлением второй стороны;
    подтверждённая запись после переноса пациентом снова ждёт подтверждения;
    у онлайн-записи сбрасывается состояние консультации."""

    def setUp(self):
        from services.models import Service
        from users.models import ClinicProfile

        self.patient = User.objects.create_user(
            email='k10-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='k10-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек',
            schedule=_all_week(), is_online_available=True,
        )
        self.clinic_user = User.objects.create_user(
            email='k10-clinic@example.com', password='password123',
            first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=self.clinic_user, name='Клиника', is_published=True)
        self.service = Service.objects.create(name='Час', category='general', duration=60)
        self.doctor.services.add(self.service)
        self.appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor, clinic=self.clinic, service=self.service,
            date=_future_day(3), time=datetime.time(10, 0),
            status=Appointment.Status.CONFIRMED,
        )
        self.url = f'/api/appointments/{self.appt.pk}/reschedule/'
        self.new_day = _future_day(4).isoformat()

    def test_reschedule_to_past_rejected(self):
        self.client.force_authenticate(user=self.patient)
        yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        response = self.client.post(self.url, {'date': yesterday, 'time': '10:00'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.date, _future_day(3))

    def test_patient_reschedule_resets_confirmed_and_notifies_doctor_and_clinic(self):
        from notifications.models import Notification

        self.client.force_authenticate(user=self.patient)
        response = self.client.post(self.url, {'date': self.new_day, 'time': '12:00'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'pending')
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, Appointment.Status.PENDING)

        for user in (self.doctor_user, self.clinic_user):
            note = Notification.objects.get(user=user)
            self.assertEqual(note.title, 'Запись перенесена')
            self.assertEqual(note.payload['appointment_id'], self.appt.id)
            self.assertEqual(note.payload['time'], '12:00')
        self.assertFalse(Notification.objects.filter(user=self.patient).exists())

    def test_doctor_reschedule_keeps_status_and_notifies_patient(self):
        from notifications.models import Notification

        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.post(self.url, {'date': self.new_day, 'time': '12:00'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'confirmed')
        note = Notification.objects.get(user=self.patient)
        self.assertIn('перенесена', note.body)
        self.assertFalse(Notification.objects.filter(user=self.doctor_user).exists())

    @patch('appointments.views.generate_meet_link', return_value='https://meet.google.com/new')
    def test_online_reschedule_resets_consultation_and_uses_service_duration(self, mock_meet):
        self.appt.is_online = True
        self.appt.consultation_status = Appointment.ConsultationStatus.FINISHED
        self.appt.doctor_joined = True
        self.appt.patient_joined = True
        self.appt.started_at = timezone.now()
        self.appt.ended_at = timezone.now()
        self.appt.doctor_egress_id = 'EG_doc'
        self.appt.doctor_egress_status = 'EGRESS_COMPLETE'
        self.appt.doctor_recording_url = 'https://example.com/doc.ogg'
        self.appt.patient_egress_id = 'EG_pat'
        self.appt.patient_egress_status = 'EGRESS_ACTIVE'
        self.appt.save()

        self.client.force_authenticate(user=self.patient)
        response = self.client.post(self.url, {'date': self.new_day, 'time': '12:00'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(mock_meet.call_args.kwargs['duration_minutes'], 60)

        self.appt.refresh_from_db()
        self.assertEqual(self.appt.consultation_status, Appointment.ConsultationStatus.CREATED)
        self.assertFalse(self.appt.doctor_joined or self.appt.patient_joined)
        self.assertIsNone(self.appt.started_at)
        self.assertIsNone(self.appt.ended_at)
        for role in ('doctor', 'patient'):
            self.assertEqual(getattr(self.appt, f'{role}_egress_id'), '')
            self.assertEqual(getattr(self.appt, f'{role}_egress_status'), '')
            self.assertEqual(getattr(self.appt, f'{role}_recording_url'), '')
        self.assertEqual(self.appt.google_meet_link, 'https://meet.google.com/new')


class MeetLinkDurationTests(APITestCase):
    """K15: событие Google Calendar длится столько, сколько услуга, а не всегда час."""

    def setUp(self):
        from services.models import Service

        self.patient = User.objects.create_user(
            email='k15-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='k15-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек',
            schedule=_all_week(), is_online_available=True,
        )
        self.service = Service.objects.create(name='45 минут', category='general', duration=45)
        self.doctor.services.add(self.service)

    @patch('appointments.utils.generate_meet_link', return_value=None)
    def test_create_passes_service_duration(self, mock_meet):
        self.client.force_authenticate(user=self.patient)
        response = self.client.post('/api/appointments/', {
            'doctor_id': self.doctor_user.id, 'service_id': self.service.id,
            'date': _future_day().isoformat(), 'time': '10:00', 'is_online': True,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_meet.call_args.kwargs['duration_minutes'], 45)

    def test_calendar_event_end_follows_duration(self):
        import sys
        from unittest.mock import MagicMock
        from django.test import override_settings
        from appointments.utils import generate_meet_link

        google = MagicMock()
        discovery = MagicMock()
        insert = discovery.build.return_value.events.return_value.insert
        insert.return_value.execute.return_value = {
            'conferenceData': {'entryPoints': [{'entryPointType': 'video', 'uri': 'https://meet/x'}]},
        }
        modules = {
            'google': google, 'google.oauth2': google.oauth2,
            'google.oauth2.credentials': google.oauth2.credentials,
            'google.auth': google.auth, 'google.auth.transport': google.auth.transport,
            'google.auth.transport.requests': google.auth.transport.requests,
            'googleapiclient': MagicMock(), 'googleapiclient.discovery': discovery,
        }
        with override_settings(
            GOOGLE_OAUTH_REFRESH_TOKEN='r', GOOGLE_OAUTH_CLIENT_ID='i', GOOGLE_OAUTH_CLIENT_SECRET='s',
        ), patch.dict(sys.modules, modules):
            link = generate_meet_link(
                datetime.date(2026, 12, 1), datetime.time(10, 0), duration_minutes=45,
            )

        self.assertEqual(link, 'https://meet/x')
        body = insert.call_args.kwargs['body']
        self.assertTrue(body['start']['dateTime'].endswith('10:00:00'))
        self.assertTrue(body['end']['dateTime'].endswith('10:45:00'))


class AllDayScheduleTests(APITestCase):
    """K23: пресет «24/7» (00:00–23:59) — последний слот 23:30–00:00 помещается."""

    def setUp(self):
        self.doctor_user = User.objects.create_user(
            email='k23-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, is_published=True, city='Бишкек',
            schedule=_all_week('00:00', '23:59'),
        )
        self.day = _future_day().isoformat()

    def test_last_slot_of_the_day_is_offered_and_bookable(self):
        response = self.client.get(
            f'/api/doctors/{self.doctor_user.id}/available-slots/', {'date': self.day},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slots = {s['time']: s['available'] for s in response.data['slots']}
        self.assertTrue(slots.get('23:30'))
        self.assertEqual(len(slots), 48)

        booked = self.client.post('/api/appointments/', {
            'doctor_id': self.doctor_user.id, 'date': self.day, 'time': '23:30',
            'guest_name': 'Гость', 'guest_phone': '+996 700 000 000',
        })
        self.assertEqual(booked.status_code, status.HTTP_201_CREATED)

    def test_24_00_end_is_understood(self):
        from appointments.utils import doctor_work_hours

        self.doctor.schedule = _all_week('09:00', '24:00')
        hours = doctor_work_hours(self.doctor, _future_day())
        self.assertIsNotNone(hours)
        self.assertEqual(hours[1] - hours[0], datetime.timedelta(hours=15))
