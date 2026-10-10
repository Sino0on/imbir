import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from services.models import Service
from users.models import DoctorProfile, User


class DoctorServiceDeleteAndPriceTests(APITestCase):
    """K19: услугу с записями врач не удаляет, а деактивирует; K21: цена."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='doctor-services-k19@example.com', password='password123',
            first_name='Алина', role=User.Role.DOCTOR,
        )
        self.profile = DoctorProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)
        self.base = {'name': 'Массаж', 'category': 'procedures'}

    def test_service_with_appointments_cannot_be_deleted_but_can_be_deactivated(self):
        service = Service.objects.create(name='Массаж', category='procedures', price=1200)
        self.profile.services.add(service)
        appointment = Appointment.objects.create(
            doctor=self.profile, service=service,
            date=datetime.date(2026, 1, 10), time=datetime.time(10, 0),
        )

        response = self.client.delete(f'/api/doctor/services/{service.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('деактивируйте', response.data['detail'])
        appointment.refresh_from_db()
        self.assertEqual(appointment.service_id, service.id)

        response = self.client.put(
            f'/api/doctor/services/{service.id}/', {**self.base, 'is_active': False}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])

    def test_service_without_appointments_is_deleted(self):
        service = Service.objects.create(name='Массаж', category='procedures')
        self.profile.services.add(service)
        response = self.client.delete(f'/api/doctor/services/{service.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Service.objects.filter(pk=service.id).exists())

    def test_negative_price_rejected_and_price_can_be_cleared(self):
        response = self.client.post('/api/doctor/services/', {**self.base, 'price': '-500'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price', response.data)

        response = self.client.post('/api/doctor/services/', {**self.base, 'price': '1500'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        detail_url = f"/api/doctor/services/{response.data['id']}/"

        response = self.client.put(detail_url, {**self.base, 'price': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['price'])

        # multipart (вместе с фото): пустая строка тоже очищает цену.
        self.client.put(detail_url, {**self.base, 'price': '900'}, format='json')
        response = self.client.put(detail_url, {**self.base, 'price': ''}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['price'])
