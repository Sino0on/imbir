from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from users.models import ClinicProfile, User


class ClinicListCityAllTests(APITestCase):
    url = '/api/clinics/'

    def setUp(self):
        self.bishkek = self._create_clinic('Клиника Бишкек', 'Бишкек')
        self.osh = self._create_clinic('Клиника Ош', 'Ош')

    def _create_clinic(self, name, city):
        user = User.objects.create_user(
            email=f'{city}@example.com',
            password='password123',
            first_name=name,
            last_name='Test',
            role=User.Role.CLINIC,
        )
        return ClinicProfile.objects.create(
            user=user, name=name, city=city, is_published=True,
        )

    def _names(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {item['name'] for item in response.data['data']}

    def test_city_all_returns_every_city(self):
        names = self._names(self.client.get(self.url, {'city': 'all'}))

        self.assertEqual(names, {'Клиника Бишкек', 'Клиника Ош'})

    @patch('core.middleware.get_city_from_ip', return_value='Ош')
    def test_city_all_ignores_ip_city(self, _mock):
        names = self._names(self.client.get(
            self.url, {'city': 'all'}, HTTP_X_FORWARDED_FOR='123.45.67.89',
        ))

        self.assertEqual(names, {'Клиника Бишкек', 'Клиника Ош'})

    def test_city_all_is_not_remembered_in_session(self):
        self.client.get(self.url, {'city': 'all'})
        names = self._names(self.client.get(self.url))

        self.assertEqual(names, {'Клиника Бишкек'})

    def test_explicit_city_still_filters(self):
        names = self._names(self.client.get(self.url, {'city': 'Ош'}))

        self.assertEqual(names, {'Клиника Ош'})
