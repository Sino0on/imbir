import datetime
from unittest.mock import patch

from django.core import mail
from django.test import TestCase

from appointments.models import Appointment
from users.models import User


class NotifyGuestTests(TestCase):
    """notify_guest: у гостя нет аккаунта и колокольчика — пишем ему SMS и письмо."""

    def _appointment(self, **extra):
        return Appointment.objects.create(
            date=datetime.date(2030, 1, 10), time=datetime.time(10, 0),
            guest_name='Гость', **extra,
        )

    @patch('users.utils.send_sms_nikita')
    def test_sends_sms_and_email(self, mock_sms):
        from notifications.utils import notify_guest

        appt = self._appointment(guest_phone='+996 700 111 222', guest_email='guest@example.com')
        notify_guest(appt, 'Запись подтверждена', 'Ваша запись на 10.01.2030 в 10:00 подтверждена.')

        mock_sms.assert_called_once_with(
            '+996 700 111 222', 'Запись подтверждена. Ваша запись на 10.01.2030 в 10:00 подтверждена.',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Запись подтверждена')
        self.assertEqual(mail.outbox[0].to, ['guest@example.com'])

    @patch('users.utils.send_sms_nikita')
    def test_skips_missing_contacts(self, mock_sms):
        from notifications.utils import notify_guest

        notify_guest(self._appointment(guest_phone='+996 700 111 222'), 'T', 'B')
        mock_sms.assert_called_once()
        self.assertEqual(len(mail.outbox), 0)

    @patch('users.utils.send_sms_nikita')
    def test_noop_for_appointment_with_account(self, mock_sms):
        from notifications.utils import notify_guest

        patient = User.objects.create_user(
            email='ng-patient@example.com', password='password123',
            first_name='Ivan', role=User.Role.PATIENT,
        )
        notify_guest(
            self._appointment(patient=patient, guest_phone='+996 700 111 222', guest_email='g@example.com'),
            'T', 'B',
        )
        mock_sms.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    @patch('users.utils.send_sms_nikita', side_effect=RuntimeError('sms down'))
    def test_sms_failure_does_not_raise(self, mock_sms):
        from notifications.utils import notify_guest

        appt = self._appointment(guest_phone='+996 700 111 222', guest_email='guest@example.com')
        with self.assertLogs('notifications.utils', level='ERROR'):
            notify_guest(appt, 'T', 'B')
        # Письмо уходит, даже если SMS упало.
        self.assertEqual(len(mail.outbox), 1)
