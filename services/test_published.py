from rest_framework import status
from rest_framework.test import APITestCase

from users.models import ClinicProfile, DoctorProfile, User

from .models import Service


class ServiceOfHiddenClinicTests(APITestCase):
    """Услуги неопубликованной клиники или клиники с заблокированным аккаунтом
    не видны ни в каталоге, ни по прямой ссылке."""

    def setUp(self):
        self.visible = Service.objects.create(
            name='УЗИ видимой', category='Диагностика',
            clinic=self._clinic('visible'),
        )
        self.unpublished = Service.objects.create(
            name='УЗИ скрытой', category='Диагностика',
            clinic=self._clinic('unpublished', published=False),
        )
        self.blocked = Service.objects.create(
            name='УЗИ заблокированной', category='Диагностика',
            clinic=self._clinic('blocked', active=False),
        )
        doctor_user = User.objects.create_user(
            email='doctor@example.com', password='password123',
            first_name='Врач', last_name='Тест', role=User.Role.DOCTOR,
        )
        doctor = DoctorProfile.objects.create(user=doctor_user, is_published=True)
        # Частная услуга врача без клиники остаётся в каталоге.
        self.private = Service.objects.create(name='Выезд на дом', category='Выезд')
        self.private.doctors.add(doctor)

    def _clinic(self, name, *, published=True, active=True):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123',
            first_name=name, last_name='Test', role=User.Role.CLINIC,
        )
        if not active:
            user.is_active = False
            user.save(update_fields=['is_active'])
        return ClinicProfile.objects.create(user=user, name=name, is_published=published)

    def test_list_excludes_services_of_hidden_clinics(self):
        response = self.client.get('/api/services/', {'city': 'all'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {item['name'] for item in response.data['data']}
        self.assertEqual(names, {'УЗИ видимой', 'Выезд на дом'})

    def test_list_by_clinic_id_of_hidden_clinic_is_empty(self):
        response = self.client.get(
            '/api/services/', {'clinic_id': self.unpublished.clinic.user_id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data'], [])

    def test_detail_of_hidden_clinic_service_is_404(self):
        for service in (self.unpublished, self.blocked):
            response = self.client.get(f'/api/services/{service.id}/')
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_of_visible_and_private_services(self):
        for service in (self.visible, self.private):
            response = self.client.get(f'/api/services/{service.id}/')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
