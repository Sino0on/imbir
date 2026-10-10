"""Регистрация клиники: сайт и координаты из step2 проходят те же правила, что
PUT профиля (N82), стаж из step1 сохраняется (N84)."""
import json
from decimal import Decimal

from rest_framework.test import APITestCase

from users.models import ClinicProfile, EmailVerificationCode, User

REGISTER_URL = '/api/auth/register/clinic/'


class ClinicRegisterWebsiteTests(APITestCase):
    email = 'clinic-register@example.com'

    def setUp(self):
        EmailVerificationCode.objects.create(email=self.email, code='1234', is_used=True)

    def _payload(self, step1=None, step2=None):
        s1 = {'name': 'Имбирь Клиник'}
        s1.update(step1 or {})
        s2 = {'email': self.email, 'city': 'Бишкек'}
        s2.update(step2 or {})
        return {
            'password': 'ClinicTest123!',
            'step1': json.dumps(s1),
            'step2': json.dumps(s2),
            'step3': '{}', 'step4': '{}', 'step5': '{}', 'step6': '{}',
            'step7': json.dumps({
                'agree_terms': True, 'agree_privacy': True,
                'agree_data_processing': True, 'agree_publishing': True,
            }),
        }

    def test_website_without_scheme_and_long_coordinates_are_normalized(self):
        response = self.client.post(REGISTER_URL, self._payload(
            step1={'experience_years': '7'},
            step2={'website': 'imbir.kg', 'location': {'lat': 42.87462134712345, 'lng': '74.5698111111111'}},
        ), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        clinic = ClinicProfile.objects.get(user__email=self.email)
        self.assertEqual(clinic.website, 'https://imbir.kg')
        self.assertEqual(clinic.latitude, Decimal('42.874621'))
        self.assertEqual(clinic.longitude, Decimal('74.569811'))
        self.assertEqual(clinic.experience_years, 7)

    def test_registered_website_passes_profile_put(self):
        self.client.post(REGISTER_URL, self._payload(step2={'website': 'imbir.kg'}), format='json')
        user = User.objects.get(email=self.email)
        self.client.force_authenticate(user=user)
        response = self.client.put('/api/clinic/profile/', {
            'name': 'Имбирь Клиник', 'website': ClinicProfile.objects.get(user=user).website,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_invalid_website_is_rejected_with_field_name(self):
        response = self.client.post(REGISTER_URL, self._payload(step2={'website': 'не сайт вовсе'}), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('website', response.data['step2'])
        self.assertFalse(User.objects.filter(email=self.email).exists())

    def test_empty_website_and_experience_are_allowed(self):
        response = self.client.post(REGISTER_URL, self._payload(step2={'website': ''}), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        clinic = ClinicProfile.objects.get(user__email=self.email)
        self.assertEqual(clinic.website, '')
        self.assertEqual(clinic.experience_years, 0)

    def test_invalid_experience_is_rejected(self):
        response = self.client.post(REGISTER_URL, self._payload(step1={'experience_years': 'много'}), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('experience_years', response.data['step1'])
