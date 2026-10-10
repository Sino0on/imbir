import datetime
from unittest import mock

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from users.models import ClinicProfile, DoctorProfile, User


class ClinicCabinetAppointmentsBase(APITestCase):
    def setUp(self):
        self.clinic_user = User.objects.create_user(
            email='stats-clinic@example.com', password='password123',
            first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=self.clinic_user, name='Клиника')
        self.doctor_user = User.objects.create_user(
            email='stats-doctor@example.com', password='password123',
            first_name='Doc', last_name='Docов', phone='+996555123456', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user)
        self.client.force_authenticate(user=self.clinic_user)
        self._hour = 8

    def _appt(self, date, st=Appointment.Status.PENDING, **kwargs):
        self._hour += 1
        return Appointment.objects.create(
            doctor=self.doctor, clinic=self.clinic, date=date,
            time=datetime.time(self._hour % 24, 0), status=st, **kwargs,
        )


class ClinicAppointmentListTests(ClinicCabinetAppointmentsBase):
    """GET /api/clinic/appointments/: контакты пациента и врача, ?ordering=."""

    def test_contacts(self):
        guest = self._appt(
            datetime.date(2030, 1, 10),
            guest_name='Гость', guest_phone='+996700111222', guest_email='guest@example.com',
        )
        patient = User.objects.create_user(
            email='reg@example.com', password='password123', first_name='Reg', phone='+996700333444',
        )
        registered = self._appt(datetime.date(2030, 1, 11), patient=patient)

        response = self.client.get('/api/clinic/appointments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = {a['id']: a for a in response.data['data']}

        self.assertEqual(items[guest.id]['patient']['phone'], '+996700111222')
        self.assertEqual(items[guest.id]['patient']['email'], 'guest@example.com')
        self.assertEqual(items[registered.id]['patient']['email'], 'reg@example.com')
        self.assertEqual(items[guest.id]['doctor']['phone'], '+996555123456')

    def test_ordering_newest_created_first(self):
        old = self._appt(datetime.date(2030, 5, 1))
        new = self._appt(datetime.date(2030, 1, 1))
        Appointment.objects.filter(pk=old.pk).update(created_at=timezone.make_aware(datetime.datetime(2026, 1, 1)))
        Appointment.objects.filter(pk=new.pk).update(created_at=timezone.make_aware(datetime.datetime(2026, 2, 1)))

        response = self.client.get('/api/clinic/appointments/', {'ordering': '-created_at'})
        self.assertEqual([a['id'] for a in response.data['data']], [new.id, old.id])
        self.assertEqual(response.data['ordering'], '-created_at')

        # Без параметра — прежний порядок по дате приёма.
        response = self.client.get('/api/clinic/appointments/')
        self.assertEqual([a['id'] for a in response.data['data']], [old.id, new.id])
        self.assertNotIn('ordering', response.data)


class ClinicStatsTests(ClinicCabinetAppointmentsBase):
    """GET /api/clinic/stats/: гости считаются пациентами, отменённые записи в
    счётчики не входят, месяц — по дате приёма и по времени Бишкека."""

    def _stats(self, now):
        with mock.patch('django.utils.timezone.now', return_value=now):
            response = self.client.get('/api/clinic/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_counts(self):
        S = Appointment.Status
        # 1 марта 2030, 02:00 по Бишкеку = 28 февраля, 20:00 UTC.
        now = timezone.make_aware(datetime.datetime(2030, 3, 1, 2, 0))

        patient = User.objects.create_user(
            email='p@example.com', password='password123', first_name='P', phone='+996 700 000 001',
        )
        self._appt(datetime.date(2030, 3, 1), S.CONFIRMED, patient=patient)
        self._appt(datetime.date(2030, 2, 20), S.COMPLETED, patient=patient)
        # Гость дважды, с разным написанием номера, — один пациент.
        self._appt(datetime.date(2030, 3, 5), S.PENDING, guest_name='Г1', guest_phone='+996 700 000 002')
        self._appt(datetime.date(2030, 3, 6), S.PENDING, guest_name='Г1', guest_phone='996700000002')
        # Гость с номером зарегистрированного пациента — тот же человек.
        self._appt(datetime.date(2030, 3, 7), S.PENDING, guest_name='P', guest_phone='+996700000001')
        # Отменённая запись — ни в записи, ни в пациенты.
        self._appt(datetime.date(2030, 3, 8), S.CANCELLED, guest_name='Г3', guest_phone='+996700000003')

        data = self._stats(now)
        self.assertEqual(data['appointments_total'], 5)
        self.assertEqual(data['appointments_this_month'], 4)
        self.assertEqual(data['patients_total'], 2)
