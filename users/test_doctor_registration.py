import json

from rest_framework.test import APITestCase

from references.models import Specialization
from users.models import DoctorProfile, PhoneVerificationCode, User


class DoctorPhoneRegistrationTests(APITestCase):
    def setUp(self):
        self.phone = '+996700000001'
        self.specialization = Specialization.objects.create(name='Флеболог')
        self.payload = {
            'password': 'DoctorTest123!',
            'step1': json.dumps({
                'full_name': 'Тестовый Врач', 'email': 'doctor-phone@example.com',
                'phone': self.phone, 'birth_date': '1990-01-01',
            }),
            'step2': '{}', 'step3': '{}', 'step4': '{}',
            'step5': json.dumps({'primary_specializations': [self.specialization.id]}),
            'step6': '{}',
            'step7': json.dumps({
                'agree_terms': True, 'agree_privacy': True,
                'agree_data_processing': True, 'agree_publishing': True,
            }),
        }

    def test_phone_confirmation_registers_doctor_with_specialization(self):
        PhoneVerificationCode.objects.create(phone=self.phone, code='1234', is_used=True)
        response = self.client.post('/api/auth/register/doctor/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        doctor = DoctorProfile.objects.get(user__email='doctor-phone@example.com')
        self.assertEqual(doctor.user.phone, self.phone)
        self.assertEqual(list(doctor.primary_specializations.all()), [self.specialization])
        self.assertIn('access', response.data)

    def test_unconfirmed_contact_does_not_create_account(self):
        response = self.client.post('/api/auth/register/doctor/', self.payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email='doctor-phone@example.com').exists())
