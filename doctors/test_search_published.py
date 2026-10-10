from rest_framework import status
from rest_framework.test import APITestCase

from services.models import Service
from users.models import ClinicProfile, User


class GlobalSearchHiddenClinicServicesTests(APITestCase):
    """Глобальный поиск и подсказки не показывают услуги скрытых клиник."""

    def setUp(self):
        Service.objects.create(
            name='Массаж видимой', category='Массаж', clinic=self._clinic('visible'),
        )
        Service.objects.create(
            name='Массаж скрытой', category='Массаж',
            clinic=self._clinic('unpublished', published=False),
        )
        Service.objects.create(
            name='Массаж заблокированной', category='Массаж',
            clinic=self._clinic('blocked', active=False),
        )
        Service.objects.create(name='Массаж на дому', category='Массаж')

    def _clinic(self, name, *, published=True, active=True):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123',
            first_name=name, last_name='Test', role=User.Role.CLINIC,
        )
        if not active:
            user.is_active = False
            user.save(update_fields=['is_active'])
        return ClinicProfile.objects.create(user=user, name=name, is_published=published)

    def _service_names(self, url):
        response = self.client.get(url, {'q': 'Массаж'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {item['name'] for item in response.data['services']}

    def test_search_excludes_services_of_hidden_clinics(self):
        self.assertEqual(
            self._service_names('/api/search/'),
            {'Массаж видимой', 'Массаж на дому'},
        )

    def test_suggest_excludes_services_of_hidden_clinics(self):
        self.assertEqual(
            self._service_names('/api/search/suggest/'),
            {'Массаж видимой', 'Массаж на дому'},
        )
