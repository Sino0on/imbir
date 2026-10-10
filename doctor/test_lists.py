import datetime
from unittest import mock

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from users.models import DoctorProfile, User


def _aware(y, m, d, h=12):
    return timezone.make_aware(datetime.datetime(y, m, d, h, 0))


class DoctorAppointmentOrderingTests(APITestCase):
    """GET /api/doctor/appointments/?ordering=... — сортировка на сервере, чтобы
    фронту не приходилось выкачивать все страницы ради «новые первыми»."""

    def setUp(self):
        self.doctor_user = User.objects.create_user(
            email='order-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user)
        # Дата приёма и время создания нарочно идут в разном порядке.
        self.far = self._appt(datetime.date(2030, 5, 1), created=_aware(2026, 1, 1))
        self.near = self._appt(datetime.date(2030, 1, 1), created=_aware(2026, 3, 1))
        self.mid = self._appt(datetime.date(2030, 3, 1), created=_aware(2026, 2, 1))
        self.client.force_authenticate(user=self.doctor_user)

    def _appt(self, date, created):
        appt = Appointment.objects.create(
            doctor=self.doctor, date=date, time=datetime.time(10, 0),
            guest_name='Гость', guest_phone='+996700000001',
        )
        Appointment.objects.filter(pk=appt.pk).update(created_at=created)
        return appt

    def _ids(self, **params):
        response = self.client.get('/api/doctor/appointments/', params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [a['id'] for a in response.data['data']], response.data

    def test_newest_created_first(self):
        ids, data = self._ids(ordering='-created_at')
        self.assertEqual(ids, [self.near.id, self.mid.id, self.far.id])
        self.assertEqual(data['ordering'], '-created_at')

    def test_newest_created_first_across_pages(self):
        ids, _ = self._ids(ordering='-created_at', page_size=1, page=2)
        self.assertEqual(ids, [self.mid.id])

    def test_oldest_created_first(self):
        ids, _ = self._ids(ordering='created_at')
        self.assertEqual(ids, [self.far.id, self.mid.id, self.near.id])

    def test_by_date(self):
        ids, _ = self._ids(ordering='date')
        self.assertEqual(ids, [self.near.id, self.mid.id, self.far.id])

    def test_default_and_unknown_keep_old_order(self):
        for params in ({}, {'ordering': 'patient__password'}):
            ids, data = self._ids(**params)
            self.assertEqual(ids, [self.far.id, self.mid.id, self.near.id])
            self.assertNotIn('ordering', data)


class DoctorPatientsLastVisitTests(APITestCase):
    """«Пациенты» и stats.patients_count: только пациенты с неотменёнными записями,
    «Последний визит» — уже состоявшийся, а не будущий или отменённый приём."""

    def setUp(self):
        self.doctor_user = User.objects.create_user(
            email='pat-doctor@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user)
        self.today = datetime.date(2030, 6, 15)
        self.client.force_authenticate(user=self.doctor_user)

    def _patient(self, n):
        return User.objects.create_user(
            email=f'pat{n}@example.com', password='password123', first_name=f'P{n}',
        )

    def _appt(self, patient, date, st, hour=10):
        return Appointment.objects.create(
            doctor=self.doctor, patient=patient, date=date,
            time=datetime.time(hour, 0), status=st,
        )

    def _get(self, url):
        with mock.patch('django.utils.timezone.localdate', return_value=self.today):
            return self.client.get(url)

    def test_last_visit_ignores_future_and_cancelled(self):
        S = Appointment.Status
        regular = self._patient(1)
        self._appt(regular, datetime.date(2030, 5, 1), S.COMPLETED)
        self._appt(regular, datetime.date(2030, 6, 10), S.CANCELLED, hour=11)
        self._appt(regular, datetime.date(2030, 7, 1), S.CONFIRMED, hour=12)

        first_timer = self._patient(2)
        self._appt(first_timer, datetime.date(2030, 11, 15), S.PENDING, hour=13)

        only_cancelled = self._patient(3)
        self._appt(only_cancelled, datetime.date(2030, 6, 1), S.CANCELLED, hour=14)

        response = self._get('/api/doctor/patients/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {p['id']: p for p in response.data['data']}

        self.assertNotIn(only_cancelled.id, rows)
        self.assertEqual(rows[regular.id]['last_visit'], '2030-05-01')
        self.assertEqual(rows[regular.id]['visits_count'], 2)
        self.assertIsNone(rows[first_timer.id]['last_visit'])
        # Реально посещавший — выше записавшегося на будущее.
        self.assertEqual([p['id'] for p in response.data['data']], [regular.id, first_timer.id])

    def test_stats_patients_count_skips_only_cancelled(self):
        S = Appointment.Status
        self._appt(self._patient(1), datetime.date(2030, 5, 1), S.COMPLETED)
        self._appt(self._patient(2), datetime.date(2030, 6, 1), S.CANCELLED, hour=11)

        response = self._get('/api/doctor/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['patients_count'], 1)
