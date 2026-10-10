"""«Настройки профиля» пациента: занятый телефон (N47) и технический email
пациента, зарегистрированного по телефону (N22)."""
from rest_framework.test import APITestCase

from users.models import User

URL = '/api/profile/'


def _body(**extra):
    return {'first_name': 'Ivan', 'last_name': 'Petrov', **extra}


class PatientProfilePhoneTests(APITestCase):
    def setUp(self):
        self.other = User.objects.create_user(
            email='other@example.com', password='password123',
            first_name='O', last_name='W', phone='+996700111222',
        )
        self.user = User.objects.create_user(
            email='me@example.com', password='password123',
            first_name='Ivan', last_name='Petrov',
        )
        self.client.force_authenticate(self.user)

    def test_taken_phone_returns_400_with_message(self):
        response = self.client.put(URL, _body(phone='+996700111222'), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            str(response.data['phone'][0]),
            'Пользователь с таким номером телефона уже зарегистрирован',
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone)

    def test_own_phone_can_be_saved_again(self):
        self.user.phone = '+996700333444'
        self.user.save(update_fields=['phone'])
        response = self.client.put(URL, _body(phone='+996700333444'), format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_blank_phone_stored_as_null(self):
        # Два аккаунта с phone='' упирались бы в unique.
        User.objects.filter(pk=self.other.pk).update(phone='')
        response = self.client.put(URL, _body(phone=''), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone)


class PatientProfilePlaceholderEmailTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='996555111222@phone.imbir.kg', password='password123',
            first_name='Ivan', last_name='Petrov', phone='+996555111222',
        )
        self.client.force_authenticate(self.user)

    def test_placeholder_email_hidden(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], '')

    def test_phone_change_regenerates_placeholder_and_frees_old_number(self):
        response = self.client.put(URL, _body(phone='+996555333444'), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['email'], '')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '996555333444@phone.imbir.kg')
        self.assertFalse(User.objects.filter(email='996555111222@phone.imbir.kg').exists())

    def test_real_email_untouched_on_phone_change(self):
        self.user.email = 'real@example.com'
        self.user.save(update_fields=['email'])
        response = self.client.put(URL, _body(phone='+996555333444'), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['email'], 'real@example.com')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'real@example.com')
