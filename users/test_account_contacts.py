"""Контакты аккаунта: привязка гостевых записей (N20) и технический email
пациента, зарегистрированного по телефону (N22)."""
import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from users.models import EmailVerificationCode, PhoneVerificationCode, User


def _guest_appointment(**kwargs):
    return Appointment.objects.create(
        date=datetime.date(2030, 1, 10), time=datetime.time(10, 0),
        guest_name='Гость', **kwargs,
    )


class PhoneRegistrationLinksGuestAppointmentsTests(APITestCase):
    """N20: после регистрации по SMS гостевые записи на тот же номер видны в
    «Истории записей», хотя гостевая форма пишет номер с пробелом."""

    url = '/api/auth/register/phone/confirm/'

    def _register(self, phone='+996700123456'):
        PhoneVerificationCode.objects.create(phone=phone, code='4321')
        return self.client.post(self.url, {
            'phone': phone, 'code': '4321', 'password': 'newpassword123',
            'first_name': 'Jan', 'last_name': 'Kovalski',
        })

    def test_guest_appointment_with_same_digits_is_linked(self):
        mine = _guest_appointment(guest_phone='+996 700123456')
        spaced = _guest_appointment(guest_phone='+996 700 123 456')
        other = _guest_appointment(guest_phone='+996 700 999 456')

        response = self._register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(phone='+996700123456')

        for appt in (mine, spaced, other):
            appt.refresh_from_db()
        self.assertEqual(mine.patient, user)
        self.assertEqual(spaced.patient, user)
        self.assertIsNone(other.patient)

        self.client.force_authenticate(user)
        history = self.client.get('/api/profile/appointments/')
        self.assertEqual(history.status_code, 200)
        ids = {row['id'] for row in history.data['data']}
        self.assertEqual(ids, {mine.id, spaced.id})

    def test_appointment_of_another_patient_is_not_taken(self):
        owner = User.objects.create_user(
            email='owner@example.com', password='password123', first_name='O', last_name='W',
        )
        appt = _guest_appointment(guest_phone='+996 700123456', patient=owner)

        self.assertEqual(self._register().status_code, status.HTTP_201_CREATED)
        appt.refresh_from_db()
        self.assertEqual(appt.patient, owner)


class EmailRegistrationLinksGuestAppointmentsTests(APITestCase):
    def test_guest_email_matched_case_insensitively(self):
        appt = _guest_appointment(guest_phone='+996 700 000 001', guest_email='Guest@Example.com')
        EmailVerificationCode.objects.create(email='guest@example.com', code='1234')

        response = self.client.post('/api/auth/register/email/confirm/', {
            'email': 'guest@example.com', 'code': '1234', 'password': 'newpassword123',
            'first_name': 'Jan', 'last_name': 'Kovalski',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        appt.refresh_from_db()
        self.assertEqual(appt.patient.email, 'guest@example.com')

    def test_unverified_client_registration_does_not_link(self):
        # /register/client/ не подтверждает почту кодом — чужие записи по
        # одному лишь адресу забирать нельзя.
        appt = _guest_appointment(guest_phone='+996 700 000 002', guest_email='guest@example.com')
        response = self.client.post('/api/auth/register/client/', {
            'email': 'guest@example.com', 'password': 'newpassword123',
            'first_name': 'Jan', 'last_name': 'Kovalski',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        appt.refresh_from_db()
        self.assertIsNone(appt.patient)


class PhonePlaceholderEmailTests(APITestCase):
    """N22: технический адрес *@phone.imbir.kg не показывается и не мешает
    зарегистрировать номер, который прежний владелец сменил в профиле."""

    def _register(self, phone):
        PhoneVerificationCode.objects.create(phone=phone, code='4321')
        return self.client.post('/api/auth/register/phone/confirm/', {
            'phone': phone, 'code': '4321', 'password': 'newpassword123',
            'first_name': 'Jan', 'last_name': 'Kovalski',
        })

    def test_placeholder_email_hidden_in_auth_responses(self):
        response = self._register('+996555111222')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['user']['email'], '')

        user = User.objects.get(phone='+996555111222')
        self.client.force_authenticate(user)
        me = self.client.get('/api/auth/me/')
        self.assertEqual(me.data['email'], '')

        login = self.client.post('/api/auth/login/', {
            'email': '+996555111222', 'password': 'newpassword123',
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['user']['email'], '')

    def test_real_email_still_returned(self):
        user = User.objects.create_user(
            email='real@example.com', password='password123', first_name='R', last_name='E',
        )
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/auth/me/').data['email'], 'real@example.com')

    def test_old_number_can_be_registered_after_owner_changed_phone(self):
        # Заглушка осталась у аккаунта, сменившего номер в обход профиля
        # (например, через админку) — регистрация не должна падать с 500.
        User.objects.create_user(
            email='996555111222@phone.imbir.kg', password='password123',
            first_name='Old', last_name='Owner', phone='+996555000000',
        )
        response = self._register('+996555111222')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(phone='+996555111222')
        self.assertTrue(user.email.endswith('@phone.imbir.kg'))
        self.assertNotEqual(user.email, '996555111222@phone.imbir.kg')

        login = self.client.post('/api/auth/login/', {
            'email': '+996555111222', 'password': 'newpassword123',
        })
        self.assertEqual(login.status_code, 200)

    def test_phone_change_via_me_regenerates_placeholder(self):
        self.assertEqual(self._register('+996555111222').status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone='+996555111222')
        self.client.force_authenticate(user)

        response = self.client.put('/api/auth/me/', {'phone': '+996555333444'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertEqual(user.email, '996555333444@phone.imbir.kg')

        self.client.force_authenticate(None)
        self.assertEqual(self._register('+996555111222').status_code, status.HTTP_201_CREATED)

    def test_me_put_taken_phone_returns_400(self):
        User.objects.create_user(
            email='taken@example.com', password='password123', first_name='T', last_name='K',
            phone='+996555777888',
        )
        user = User.objects.create_user(
            email='me@example.com', password='password123', first_name='M', last_name='E',
        )
        self.client.force_authenticate(user)
        response = self.client.put('/api/auth/me/', {'phone': '+996555777888'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.data)
