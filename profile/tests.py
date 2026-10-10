from datetime import time as dt_time, timedelta

from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from appointments.models import Appointment
from references.models import Specialization
from reviews.models import Review
from users.models import DoctorProfile, ClinicProfile, DoctorClinicLink, ClinicBranch
from services.models import Service

User = get_user_model()


class ProfileFavoritesTests(APITestCase):
    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            email='patient@example.com',
            password='password123',
            first_name='John',
            last_name='Doe',
            role=User.Role.PATIENT
        )

        # Create doctor profile
        self.doctor_user = User.objects.create_user(
            email='doctor@example.com',
            password='password123',
            first_name='Doctor',
            last_name='Who',
            role=User.Role.DOCTOR
        )
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.doctor_user,
            is_published=True
        )

        # Create clinic profile
        self.clinic_user = User.objects.create_user(
            email='clinic@example.com',
            password='password123',
            first_name='Clinic',
            last_name='One',
            role=User.Role.CLINIC
        )
        self.clinic_profile = ClinicProfile.objects.create(
            user=self.clinic_user,
            name='Clinic One',
            is_published=True
        )

        DoctorClinicLink.objects.create(
            doctor=self.doctor_profile,
            clinic=self.clinic_profile,
            is_active=True
        )

        # Create service
        self.service = Service.objects.create(
            name='Ультразвук',
            price=1500.00,
            category='diagnostics',
            is_active=True,
            clinic=self.clinic_profile,
        )

        self.favorites_url = '/api/profile/favorites/'

    def test_unauthenticated_access(self):
        response = self.client.get(self.favorites_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_favorites_crud_lifecycle(self):
        self.client.force_authenticate(user=self.user)

        # 1. Get initial empty favorites
        response = self.client.get(self.favorites_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['doctors']), 0)
        self.assertEqual(len(response.data['data']['clinics']), 0)
        self.assertEqual(len(response.data['data']['services']), 0)

        # 2. Add doctor
        response = self.client.post(self.favorites_url, {'target_type': 'doctor', 'target_id': self.doctor_user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['data']['doctors']), 1)
        self.assertEqual(response.data['data']['doctors'][0]['id'], self.doctor_user.id)
        self.assertEqual(
            response.data['data']['doctors'][0]['clinic'],
            {'id': self.clinic_user.id, 'name': 'Clinic One'}
        )

        # 3. Add clinic
        response = self.client.post(self.favorites_url, {'target_type': 'clinic', 'target_id': self.clinic_user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['data']['clinics']), 1)
        self.assertEqual(response.data['data']['clinics'][0]['id'], self.clinic_user.id)

        # 4. Add service
        response = self.client.post(self.favorites_url, {'target_type': 'service', 'target_id': self.service.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['data']['services']), 1)
        self.assertEqual(response.data['data']['services'][0]['id'], self.service.id)
        self.assertEqual(
            response.data['data']['services'][0]['clinic'],
            {'id': self.clinic_user.id, 'name': 'Clinic One'}
        )

        # 5. Retrieve list again and verify M2M
        response = self.client.get(self.favorites_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['doctors']), 1)
        self.assertEqual(len(response.data['data']['clinics']), 1)
        self.assertEqual(len(response.data['data']['services']), 1)

        # 6. Delete doctor using body
        response = self.client.delete(self.favorites_url, {'target_type': 'doctor', 'target_id': self.doctor_user.id})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 7. Delete clinic using query parameters
        response = self.client.delete(f'{self.favorites_url}?target_type=clinic&target_id={self.clinic_user.id}')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 8. Check remaining service in favorites
        response = self.client.get(self.favorites_url)
        self.assertEqual(len(response.data['data']['doctors']), 0)
        self.assertEqual(len(response.data['data']['clinics']), 0)
        self.assertEqual(len(response.data['data']['services']), 1)

    def test_validation_errors(self):
        self.client.force_authenticate(user=self.user)

        # Non-existent doctor
        response = self.client.post(self.favorites_url, {'target_type': 'doctor', 'target_id': 9999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Non-existent clinic
        response = self.client.post(self.favorites_url, {'target_type': 'clinic', 'target_id': 9999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Non-existent service
        response = self.client.post(self.favorites_url, {'target_type': 'service', 'target_id': 9999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PatientAppointmentHistoryTests(APITestCase):
    url = '/api/profile/appointments/'

    def setUp(self):
        self.patient = User.objects.create_user(
            email='history-patient@example.com', password='password123',
            first_name='Иван', last_name='Петров', role=User.Role.PATIENT,
        )
        doctor_user = User.objects.create_user(
            email='history-doctor@example.com', password='password123',
            first_name='Анна', last_name='Врачева', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=doctor_user, is_published=True, rating='4.50')
        self.doctor.primary_specializations.add(Specialization.objects.create(name='Кардиолог'))

        clinic_a_user = User.objects.create_user(
            email='history-clinic-a@example.com', password='password123', role=User.Role.CLINIC,
        )
        self.clinic_a = ClinicProfile.objects.create(
            user=clinic_a_user, name='Клиника A', address='ул. Первая, 1',
        )
        clinic_b_user = User.objects.create_user(
            email='history-clinic-b@example.com', password='password123', role=User.Role.CLINIC,
        )
        self.clinic_b = ClinicProfile.objects.create(
            user=clinic_b_user, name='Клиника B', address='ул. Вторая, 2',
        )
        # Первая клиника врача — A, а записи ниже идут в B.
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic_a, is_active=True)
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic_b, is_active=True)

        self.client.force_authenticate(user=self.patient)
        self.today = timezone.localdate()

    def _appt(self, days, status=Appointment.Status.CONFIRMED, **kwargs):
        kwargs.setdefault('doctor', self.doctor)
        kwargs.setdefault('clinic', self.clinic_b)
        return Appointment.objects.create(
            patient=self.patient, date=self.today + timedelta(days=days),
            time=dt_time(10, 0), status=status, **kwargs,
        )

    def _ids(self, response):
        return [item['id'] for item in response.data['data']]

    def test_upcoming_tab_skips_past_visits_and_orders_nearest_first(self):
        far = self._appt(10)
        near = self._appt(1)
        middle = self._appt(5, status=Appointment.Status.PENDING)
        past = self._appt(-3)
        self._appt(2, status=Appointment.Status.CANCELLED)

        response = self.client.get(self.url, {'tab': 'upcoming', 'status': 'upcoming'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._ids(response), [near.id, middle.id, far.id])
        self.assertNotIn(past.id, self._ids(response))
        self.assertTrue(all(item['is_past'] is False for item in response.data['data']))

    def test_past_tab_includes_overdue_active_visits_newest_first(self):
        self._appt(3)
        overdue = self._appt(-1)
        cancelled = self._appt(-2, status=Appointment.Status.CANCELLED)
        completed = self._appt(-5, status=Appointment.Status.COMPLETED)

        response = self.client.get(self.url, {'tab': 'past'})

        self.assertEqual(self._ids(response), [overdue.id, cancelled.id, completed.id])
        self.assertTrue(all(item['is_past'] is True for item in response.data['data']))

        response = self.client.get(self.url, {'tab': 'past', 'status': 'cancelled'})
        self.assertEqual(self._ids(response), [cancelled.id])

    def test_visit_stays_upcoming_during_join_window(self):
        # Началась 5 минут назад: окно подключения к консультации ещё открыто.
        started = timezone.localtime() - timedelta(minutes=5)
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor, date=started.date(),
            time=started.time().replace(microsecond=0), status=Appointment.Status.CONFIRMED,
            is_online=True,
        )
        with self.settings(LIVEKIT_JOIN_WINDOW_MINUTES=15):
            response = self.client.get(self.url, {'tab': 'upcoming'})
        self.assertEqual(self._ids(response), [appt.id])

    def test_old_status_param_still_works(self):
        past = self._appt(-3)
        future = self._appt(3)
        response = self.client.get(self.url, {'status': 'upcoming'})
        self.assertEqual(set(self._ids(response)), {past.id, future.id})

    def test_doctor_card_data_comes_with_appointment(self):
        self._appt(1)
        response = self.client.get(self.url, {'tab': 'upcoming'})
        doctor = response.data['data'][0]['doctor']
        self.assertEqual(doctor['id'], self.doctor.user_id)
        self.assertEqual(doctor['full_name'], self.doctor.user.full_name)
        self.assertEqual(doctor['specialty'], 'Кардиолог')
        self.assertEqual(doctor['rating'], '4.50')
        self.assertIn('photo', doctor)
        self.assertTrue(doctor['is_published'])

    def test_unpublished_doctor_still_has_card_data(self):
        self.doctor.is_published = False
        self.doctor.save(update_fields=['is_published'])
        self._appt(1)
        response = self.client.get(self.url, {'tab': 'upcoming'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        doctor = response.data['data'][0]['doctor']
        self.assertEqual(doctor['specialty'], 'Кардиолог')
        self.assertFalse(doctor['is_published'])

    def test_clinic_address_is_from_appointment_clinic(self):
        self._appt(1)
        response = self.client.get(self.url, {'tab': 'upcoming'})
        self.assertEqual(
            response.data['data'][0]['clinic'],
            {'id': self.clinic_b.user_id, 'name': 'Клиника B', 'address': 'ул. Вторая, 2'},
        )

    def test_clinic_address_prefers_service_branch(self):
        branch = ClinicBranch.objects.create(clinic=self.clinic_b, address='пр. Филиальный, 7')
        service = Service.objects.create(
            name='ЭКГ', category='diagnostics', clinic=self.clinic_b, branch=branch,
        )
        self._appt(1, service=service)
        response = self.client.get(self.url, {'tab': 'upcoming'})
        self.assertEqual(response.data['data'][0]['clinic']['address'], 'пр. Филиальный, 7')

    def test_diagnosis_and_recommendations_visible_to_patient(self):
        self._appt(
            -1, status=Appointment.Status.COMPLETED,
            diagnosis='ОРВИ', recommendations='Пить больше воды',
        )
        response = self.client.get(self.url, {'tab': 'past'})
        item = response.data['data'][0]
        self.assertEqual(item['diagnosis'], 'ОРВИ')
        self.assertEqual(item['recommendations'], 'Пить больше воды')

    def test_can_review_false_when_doctor_already_reviewed(self):
        first = self._appt(-5, status=Appointment.Status.COMPLETED)
        second = self._appt(-1, status=Appointment.Status.COMPLETED)
        response = self.client.get(self.url, {'tab': 'past'})
        self.assertTrue(all(item['can_review'] for item in response.data['data']))

        # Отзыв по первой записи — второй тому же врачу бэк уже не примет.
        Review.objects.create(
            author=self.patient, appointment=first, target_type=Review.TargetType.DOCTOR,
            doctor=self.doctor, rating=5,
        )
        response = self.client.get(self.url, {'tab': 'past'})
        flags = {item['id']: item['can_review'] for item in response.data['data']}
        self.assertEqual(flags, {first.id: False, second.id: False})

    def test_can_review_false_after_review_from_doctor_page(self):
        appt = self._appt(-1, status=Appointment.Status.COMPLETED)
        Review.objects.create(
            author=self.patient, target_type=Review.TargetType.DOCTOR, doctor=self.doctor, rating=4,
        )
        response = self.client.get(self.url, {'tab': 'past'})
        self.assertEqual(response.data['data'][0]['id'], appt.id)
        self.assertFalse(response.data['data'][0]['can_review'])

    def test_can_review_for_clinic_only_visit(self):
        self._appt(-1, status=Appointment.Status.COMPLETED, doctor=None)
        response = self.client.get(self.url, {'tab': 'past'})
        self.assertTrue(response.data['data'][0]['can_review'])

        Review.objects.create(
            author=self.patient, target_type=Review.TargetType.CLINIC, clinic=self.clinic_b, rating=4,
        )
        response = self.client.get(self.url, {'tab': 'past'})
        self.assertFalse(response.data['data'][0]['can_review'])

    def test_can_review_false_for_unpublished_doctor(self):
        self.doctor.is_published = False
        self.doctor.save(update_fields=['is_published'])
        self._appt(-1, status=Appointment.Status.COMPLETED)
        response = self.client.get(self.url, {'tab': 'past'})
        self.assertFalse(response.data['data'][0]['can_review'])

    def test_reviews_queried_once_per_list(self):
        for days in range(1, 6):
            self._appt(-days, status=Appointment.Status.COMPLETED)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.url, {'tab': 'past'})
        review_queries = [q for q in ctx.captured_queries if 'FROM "reviews_review"' in q['sql']]
        self.assertEqual(len(review_queries), 1)
