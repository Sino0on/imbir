from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from services.models import Service
from users.models import ClinicProfile, DoctorProfile, User


def _create_doctor(email, last_name, city, price=None):
    user = User.objects.create_user(
        email=email,
        password='password123',
        first_name='Терапевт',
        last_name=last_name,
        role=User.Role.DOCTOR,
    )
    return DoctorProfile.objects.create(
        user=user, is_published=True, city=city, consultation_price=price,
    )


def _create_clinic(email, name, city):
    user = User.objects.create_user(
        email=email,
        password='password123',
        first_name=name,
        last_name='Test',
        role=User.Role.CLINIC,
    )
    return ClinicProfile.objects.create(
        user=user, name=name, city=city, is_published=True,
    )


class DoctorListCityAllTests(APITestCase):
    url = '/api/doctors/'

    def setUp(self):
        self.bishkek = _create_doctor('b@example.com', 'Бишкекский', 'Бишкек')
        self.osh = _create_doctor('o@example.com', 'Ошский', 'Ош')

    def _ids(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {item['id'] for item in response.data['data']}

    def test_city_all_returns_every_city(self):
        ids = self._ids(self.client.get(self.url, {'city': 'all'}))

        self.assertEqual(ids, {self.bishkek.user_id, self.osh.user_id})

    @patch('core.middleware.get_city_from_ip', return_value='Ош')
    def test_city_all_ignores_ip_city(self, _mock):
        ids = self._ids(self.client.get(
            self.url, {'city': 'all'}, HTTP_X_FORWARDED_FOR='123.45.67.89',
        ))

        self.assertEqual(ids, {self.bishkek.user_id, self.osh.user_id})

    def test_city_all_is_not_remembered_in_session(self):
        self.client.get(self.url, {'city': 'all'})
        # Без city — снова город по умолчанию, а не «all» из сессии.
        ids = self._ids(self.client.get(self.url))

        self.assertEqual(ids, {self.bishkek.user_id})

    def test_without_city_keeps_default_city(self):
        ids = self._ids(self.client.get(self.url))

        self.assertEqual(ids, {self.bishkek.user_id})


class DoctorConsultationPriceFieldTests(APITestCase):
    def setUp(self):
        self.doctor = _create_doctor(
            'p@example.com', 'Платный', 'Бишкек', price='1500.00',
        )
        self.no_price = _create_doctor('n@example.com', 'Бесценный', 'Бишкек')

    def test_list_returns_consultation_price(self):
        response = self.client.get('/api/doctors/', {'city': 'Бишкек'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prices = {
            item['id']: item['consultation_price']
            for item in response.data['data']
        }
        self.assertEqual(prices[self.doctor.user_id], '1500.00')
        self.assertIsNone(prices[self.no_price.user_id])

    def test_detail_returns_consultation_price(self):
        response = self.client.get(f'/api/doctors/{self.doctor.user_id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['consultation_price'], '1500.00')


class SearchSuggestCityTests(APITestCase):
    suggest_url = '/api/search/suggest/'

    def setUp(self):
        self.bishkek_doctor = _create_doctor('sb@example.com', 'Кардиобишкек', 'Бишкек')
        self.osh_doctor = _create_doctor('so@example.com', 'Кардиош', 'Ош')
        self.bishkek_clinic = _create_clinic('cb@example.com', 'Кардио Бишкек', 'Бишкек')
        self.osh_clinic = _create_clinic('co@example.com', 'Кардио Ош', 'Ош')
        Service.objects.create(
            name='Кардио ЭКГ Бишкек', category='Диагностика',
            clinic=self.bishkek_clinic,
        )
        Service.objects.create(
            name='Кардио ЭКГ Ош', category='Диагностика', clinic=self.osh_clinic,
        )
        private = Service.objects.create(name='Кардио выезд', category='Выезд')
        private.doctors.add(self.osh_doctor)

    def _get(self, params):
        response = self.client.get(self.suggest_url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_city_param_limits_suggestions(self):
        data = self._get({'q': 'Кардио', 'city': 'Ош'})

        self.assertEqual(
            {d['id'] for d in data['doctors']}, {self.osh_doctor.user_id},
        )
        self.assertEqual({c['name'] for c in data['clinics']}, {'Кардио Ош'})
        self.assertEqual(
            {s['name'] for s in data['services']},
            {'Кардио ЭКГ Ош', 'Кардио выезд'},
        )

    def test_without_city_searches_every_city(self):
        data = self._get({'q': 'Кардио'})

        self.assertEqual(len(data['doctors']), 2)
        self.assertEqual(len(data['clinics']), 2)
        self.assertEqual(len(data['services']), 3)

    def test_city_all_searches_every_city(self):
        data = self._get({'q': 'Кардио', 'city': 'all'})

        self.assertEqual(len(data['clinics']), 2)

    def test_full_search_accepts_city(self):
        response = self.client.get('/api/search/', {'q': 'Кардио', 'city': 'Бишкек'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {c['name'] for c in response.data['clinics']}, {'Кардио Бишкек'},
        )
