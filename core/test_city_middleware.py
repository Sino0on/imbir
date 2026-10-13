from unittest import mock

from django.contrib.sessions.models import Session
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from core import middleware
from users.models import DoctorProfile, User

PUBLIC_IP = '8.8.8.8'


class CityDetectionTests(APITestCase):
    url = '/api/doctors/'

    def setUp(self):
        cache.clear()
        for email, city in (('b@example.com', 'Бишкек'), ('o@example.com', 'Ош')):
            user = User.objects.create_user(
                email=email, password='password123', first_name='Doc', role=User.Role.DOCTOR,
            )
            DoctorProfile.objects.create(user=user, is_published=True, city=city)

    def _cities(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {d['city'] for d in response.data['data']}

    @mock.patch('core.middleware.get_city_from_ip', return_value='Ош')
    def test_ip_city_is_looked_up_once_per_ip(self, lookup):
        for _ in range(3):
            cities = self._cities(self.client.get(self.url, HTTP_X_FORWARDED_FOR=PUBLIC_IP))

        self.assertEqual(cities, {'Ош'})
        lookup.assert_called_once_with(PUBLIC_IP)

    @mock.patch('core.middleware.get_city_from_ip', return_value=None)
    def test_failed_lookup_is_cached_and_falls_back_to_default(self, lookup):
        for _ in range(3):
            cities = self._cities(self.client.get(self.url, HTTP_X_FORWARDED_FOR=PUBLIC_IP))

        self.assertEqual(cities, {'Бишкек'})
        lookup.assert_called_once()

    @mock.patch('core.middleware.get_city_from_ip')
    def test_explicit_city_skips_lookup(self, lookup):
        cities = self._cities(self.client.get(self.url, {'city': 'Ош'}, HTTP_X_FORWARDED_FOR=PUBLIC_IP))

        self.assertEqual(cities, {'Ош'})
        lookup.assert_not_called()

    @mock.patch('core.middleware.get_city_from_ip')
    def test_endpoints_without_city_never_look_it_up(self, lookup):
        response = self.client.get('/api/blog/', HTTP_X_FORWARDED_FOR=PUBLIC_IP)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        lookup.assert_not_called()

    def test_city_is_not_written_to_sessions(self):
        with mock.patch('core.middleware.get_city_from_ip', return_value='Ош'):
            self.client.get(self.url, {'city': 'Ош'})
            self.client.get(self.url, HTTP_X_FORWARDED_FOR=PUBLIC_IP)

        self.assertEqual(Session.objects.count(), 0)


class GetCityFromIpTests(APITestCase):
    @mock.patch('core.middleware.urllib.request.urlopen')
    def test_private_and_local_addresses_are_not_sent(self, urlopen):
        for ip in ('127.0.0.1', '192.168.48.1', '10.0.0.5', '172.17.0.1', '::1', 'garbage', ''):
            self.assertIsNone(middleware.get_city_from_ip(ip))

        urlopen.assert_not_called()

    @mock.patch('core.middleware.urllib.request.urlopen', side_effect=TimeoutError('timed out'))
    def test_public_address_uses_short_timeout(self, urlopen):
        self.assertIsNone(middleware.get_city_from_ip(PUBLIC_IP))

        self.assertEqual(urlopen.call_args.kwargs['timeout'], 1)
